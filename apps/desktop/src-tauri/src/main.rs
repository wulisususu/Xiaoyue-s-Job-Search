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

impl CoreSidecar {
    fn launch() -> Option<CoreSidecar> {
        let core_bin = find_core_bin()?;
        let port = pick_free_port().ok()?;
        let session_token = generate_session_token();
        let data_dir = std::env::var("XIAOYUE_DATA_DIR").unwrap_or_else(|_| {
            let home = std::env::var("USERPROFILE").unwrap_or_else(|_| ".".into());
            format!("{}\\.xiaoyue-job-search", home)
        });

        let child = Command::new(&core_bin)
            .env("XIAOYUE_PORT", port.to_string())
            .env("XIAOYUE_SESSION_TOKEN", &session_token)
            .env("XIAOYUE_DATA_DIR", &data_dir)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .ok()?;

        let endpoint = format!("127.0.0.1:{}", port);
        if !wait_until_healthy(&endpoint, Duration::from_secs(30)) {
            eprintln!("core-api sidecar did not become healthy in time");
        }
        Some(CoreSidecar {
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
    base_url: String,
    session_token: String,
}

#[tauri::command]
fn core_endpoint(state: tauri::State<'_, Mutex<Option<CoreSidecar>>>) -> Option<CoreEndpointInfo> {
    let guard = state.lock().ok()?;
    guard.as_ref().map(|sidecar| CoreEndpointInfo {
        base_url: format!("http://{}", sidecar.endpoint),
        session_token: sidecar.session_token.clone(),
    })
}

fn main() {
    let sidecar = Mutex::new(CoreSidecar::launch());
    tauri::Builder::default()
        .manage(sidecar)
        .invoke_handler(tauri::generate_handler![core_endpoint])
        .build(tauri::generate_context!())
        .expect("error while building Xiaoyue Job Search")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                if let Some(state) = app_handle.try_state::<Mutex<Option<CoreSidecar>>>() {
                    if let Ok(mut guard) = state.lock() {
                        if let Some(sidecar) = guard.as_mut() {
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
}
