use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::Manager;

/// Runtime handle for the bundled core-api sidecar.
struct CoreSidecar {
    child: Option<Child>,
    endpoint: String,
    session_token: String,
}

/// Locate the bundled core-api executable next to the Tauri binary
/// (`xiaoyue-core-api.exe` or `xiaoyue-core-api-<target-triple>.exe`).
/// Returns None in dev mode, where the core is started by scripts/dev.ps1.
fn find_core_bin() -> Option<PathBuf> {
    if let Ok(path) = std::env::var("XIAOYUE_CORE_BIN") {
        let path = PathBuf::from(path);
        if path.is_file() {
            return Some(path);
        }
    }
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let mut candidates = vec![
        exe_dir.join("xiaoyue-core-api.exe"),
        exe_dir.join("core-api").join("xiaoyue-core-api.exe"),
    ];
    if let Ok(triple) = std::env::var("TARGET_TRIPLE") {
        candidates.push(exe_dir.join(format!("xiaoyue-core-api-{}.exe", triple)));
    }
    candidates.into_iter().find(|p| p.is_file())
}

/// Grab a free loopback port by binding port 0 and releasing it. There is a
/// small race window before the sidecar binds, which is acceptable for a
/// single-user desktop app.
fn pick_free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind("127.0.0.1:0")?;
    let port = listener.local_addr()?.port();
    drop(listener);
    Ok(port)
}

/// OS CSPRNG (BCryptGenRandom on Windows): 256-bit per-launch secret,
/// hex-encoded. The token dies with the process and is never persisted.
fn generate_session_token() -> String {
    let mut bytes = [0u8; 32];
    getrandom::fill(&mut bytes).expect("OS CSPRNG unavailable");
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// Poll /api/health on the sidecar until it answers.
fn wait_until_healthy(endpoint: &str, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if let Ok(mut stream) = TcpStream::connect(endpoint) {
            let request = "GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n";
            let mut buffer = String::new();
            if stream.write_all(request.as_bytes()).is_ok()
                && stream.read_to_string(&mut buffer).is_ok()
                && buffer.contains("200")
            {
                return true;
            }
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

fn log_dir(data_dir: &str) -> PathBuf {
    PathBuf::from(data_dir).join("logs")
}

/// One stderr + one stdout file per launch (uvicorn logs to both); appending
/// two handles into a single file is unreliable on Windows, hence the pair.
fn open_log_files(dir: &PathBuf) -> std::io::Result<(std::fs::File, std::fs::File)> {
    std::fs::create_dir_all(dir)?;
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0);
    let out = std::fs::OpenOptions::new().create(true).append(true)
        .open(dir.join(format!("core-{}-{}.out.log", stamp, std::process::id())))?;
    let err = std::fs::OpenOptions::new().create(true).append(true)
        .open(dir.join(format!("core-{}-{}.err.log", stamp, std::process::id())))?;
    Ok((out, err))
}

/// Keep only the newest `keep` per-launch core log files; never touch
/// anything that does not match the core-*.log naming scheme.
fn prune_old_logs(dir: &PathBuf, keep: usize) {
    let mut logs: Vec<(std::path::PathBuf, std::time::SystemTime)> = match std::fs::read_dir(dir) {
        Ok(entries) => entries
            .filter_map(|e| e.ok())
            .filter(|e| {
                let n = e.file_name().to_string_lossy().to_string();
                n.starts_with("core-") && (n.ends_with(".out.log") || n.ends_with(".err.log"))
            })
            .filter_map(|e| e.metadata().ok().and_then(|m| m.modified().ok()).map(|t| (e.path(), t)))
            .collect(),
        Err(_) => return,
    };
    logs.sort_by_key(|(_, t)| *t);
    let excess = logs.len().saturating_sub(keep);
    for (path, _) in logs.into_iter().take(excess) {
        let _ = std::fs::remove_file(path);
    }
}

/// Explicit launch outcome: dev (nothing bundled) stays quiet, a bundled
/// but broken sidecar surfaces a diagnosable reason to the UI.
enum SidecarLaunch {
    Launched(CoreSidecar),
    /// Dev shell: nothing bundled, nothing to show (expected path).
    NotBundled,
    /// Bundled but failed: the user must see a diagnosable reason.
    Failed(String),
}

impl CoreSidecar {
    fn launch() -> SidecarLaunch {
        let core_bin = match find_core_bin() {
            Some(path) => path,
            None => return SidecarLaunch::NotBundled,
        };
        let port = match pick_free_port() {
            Ok(port) => port,
            Err(e) => return SidecarLaunch::Failed(format!("无法分配本地端口: {e}")),
        };
        let session_token = generate_session_token();
        let data_dir = std::env::var("XIAOYUE_DATA_DIR").unwrap_or_else(|_| {
            let home = std::env::var("USERPROFILE").unwrap_or_else(|_| ".".into());
            format!("{}\\.xiaoyue-job-search", home)
        });

        let logs = log_dir(&data_dir);
        prune_old_logs(&logs, 20);
        let (out_log, err_log) = match open_log_files(&logs) {
            Ok(files) => Some(files),
            Err(e) => {
                eprintln!("cannot open sidecar log files: {e}");
                None
            }
        }
        .map(|(out, err)| (Some(out), Some(err)))
        .unwrap_or((None, None));

        let mut command = Command::new(&core_bin);
        command.env("XIAOYUE_PORT", port.to_string())
            .env("XIAOYUE_SESSION_TOKEN", &session_token)
            .env("XIAOYUE_DATA_DIR", &data_dir);
        match out_log {
            Some(file) => {
                command.stdout(Stdio::from(file));
            }
            None => {
                command.stdout(Stdio::null());
            }
        }
        match err_log {
            Some(file) => {
                command.stderr(Stdio::from(file));
            }
            None => {
                command.stderr(Stdio::null());
            }
        }
        let child = match command.spawn() {
            Ok(child) => child,
            Err(e) => return SidecarLaunch::Failed(format!("spawn 失败: {e}")),
        };

        let endpoint = format!("127.0.0.1:{}", port);
        if !wait_until_healthy(&endpoint, Duration::from_secs(30)) {
            // Health probe failed: do not leak an orphan child process.
            let mut child = child;
            let _ = child.kill();
            let _ = child.wait();
            return SidecarLaunch::Failed(
                "sidecar 30 秒内未通过健康检查，详见数据目录 logs/ 下 core-*.err.log".into(),
            );
        }
        SidecarLaunch::Launched(CoreSidecar {
            child: Some(child),
            endpoint,
            session_token,
        })
    }

    fn shutdown(&mut self) {
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
    }
}

#[derive(serde::Serialize)]
struct CoreEndpointInfo {
    base_url: Option<String>,
    session_token: Option<String>,
    status: String,
    detail: Option<String>,
}

struct CoreSidecarState {
    sidecar: Option<CoreSidecar>,
    failure_detail: Option<String>,
}

impl CoreSidecarState {
    fn from_launch(launch: SidecarLaunch) -> CoreSidecarState {
        match launch {
            SidecarLaunch::Launched(sidecar) => CoreSidecarState {
                sidecar: Some(sidecar),
                failure_detail: None,
            },
            SidecarLaunch::NotBundled => CoreSidecarState {
                sidecar: None,
                failure_detail: None,
            },
            SidecarLaunch::Failed(detail) => CoreSidecarState {
                sidecar: None,
                failure_detail: Some(detail),
            },
        }
    }
}

#[tauri::command]
fn core_endpoint(state: tauri::State<'_, Mutex<CoreSidecarState>>) -> CoreEndpointInfo {
    match state.lock() {
        Ok(guard) => match &guard.sidecar {
            Some(sidecar) => CoreEndpointInfo {
                base_url: Some(format!("http://{}", sidecar.endpoint)),
                session_token: Some(sidecar.session_token.clone()),
                status: "launched".into(),
                detail: None,
            },
            None => match &guard.failure_detail {
                Some(detail) => CoreEndpointInfo {
                    base_url: None,
                    session_token: None,
                    status: "failed".into(),
                    detail: Some(detail.clone()),
                },
                None => CoreEndpointInfo {
                    base_url: None,
                    session_token: None,
                    status: "unbundled".into(),
                    detail: None,
                },
            },
        },
        Err(_) => CoreEndpointInfo {
            base_url: None,
            session_token: None,
            status: "failed".into(),
            detail: Some("internal state poisoned".into()),
        },
    }
}

fn main() {
    let sidecar = Mutex::new(CoreSidecarState::from_launch(CoreSidecar::launch()));
    tauri::Builder::default()
        .manage(sidecar)
        .invoke_handler(tauri::generate_handler![core_endpoint])
        .build(tauri::generate_context!())
        .expect("error while building Xiaoyue Job Search")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<Mutex<CoreSidecarState>>() {
                    if let Ok(mut guard) = state.lock() {
                        if let Some(sidecar) = guard.sidecar.as_mut() {
                            sidecar.shutdown();
                        }
                    }
                }
            }
        });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn session_token_is_256_bit_hex() {
        let token = generate_session_token();
        assert_eq!(token.len(), 64, "256-bit => 64 hex chars");
        assert!(token.chars().all(|c| c.is_ascii_hexdigit()));
    }

    #[test]
    fn session_token_differs_between_launches() {
        assert_ne!(generate_session_token(), generate_session_token());
    }

    #[test]
    fn log_file_names_are_launch_unique_and_pattern_safe() {
        let dir = std::env::temp_dir().join("xiaoyue-log-test");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        let (mut out, mut err) = open_log_files(&dir).unwrap();
        writeln!(out, "stdout line").unwrap();
        writeln!(err, "stderr line").unwrap();
        let names: Vec<String> = std::fs::read_dir(&dir).unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        assert_eq!(names.iter().filter(|n| n.starts_with("core-") && n.ends_with(".out.log")).count(), 1);
        assert_eq!(names.iter().filter(|n| n.starts_with("core-") && n.ends_with(".err.log")).count(), 1);
        let out_first = names.iter().find(|n| n.ends_with(".out.log")).unwrap();
        let err_first = names.iter().find(|n| n.ends_with(".err.log")).unwrap();
        assert_ne!(out_first, err_first);
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn prune_keeps_only_newest_logs() {
        let dir = std::env::temp_dir().join("xiaoyue-log-prune-test");
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        for i in 0..12 {
            let path = dir.join(format!("core-20260917-{:04}-pid.out.log", i));
            std::fs::write(&path, "x").unwrap();
            std::fs::write(&path.with_extension("err.log"), "x").unwrap();
        }
        std::fs::write(dir.join("unrelated.log"), "x").unwrap();
        prune_old_logs(&dir, 5);
        let remaining: Vec<String> = std::fs::read_dir(&dir).unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().to_string())
            .collect();
        assert_eq!(remaining.iter().filter(|n| n.starts_with("core-")).count(), 5);
        assert!(remaining.contains(&"unrelated.log".to_string()));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
