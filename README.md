# Xiaoyue's Job Search

央国企岗位雷达、个人求职知识库、简历版本库、AI 网申 Agent 与投递 CRM 的本地优先桌面工作台。

## V1 技术栈

- Node.js 20+
- Python 3.11+
- Rust stable
- Microsoft Edge WebView2 Runtime
- Tauri 2 + React + TypeScript
- FastAPI + SQLAlchemy + SQLite

## 本地开发（Windows PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".\services\core-api[dev]"
npm install
.\scripts\test.ps1
.\scripts\dev.ps1
```

默认本地数据目录为 `%LOCALAPPDATA%\XiaoyueJobSearch`。可通过环境变量 `XIAOYUE_DATA_DIR` 覆盖。

## 当前里程碑

MVP Foundation 只建立桌面壳、本地 Core API、SQLite、文件 Vault 根目录与测试基线。简历解析、招聘数据采集、Browser Agent、AI 填表将在后续里程碑接入。

## MVP Foundation 验收清单

- [x] Local API 提供 `/api/health`
- [x] SQLite 数据库写入 `XIAOYUE_DATA_DIR`
- [x] Local Vault 根目录自动创建
- [x] 桌面 UI 定义六个一级入口：首页、岗位雷达、投递中心、我的资料、简历库、设置
- [x] UI 接入本地 Core 健康状态
- [x] Core pytest 基线已建立
- [ ] Web 测试通过（由 GitHub Actions / 本机 npm install 后验证）
- [ ] Frontend production build 通过（由 GitHub Actions / 本机 npm install 后验证）
- [ ] Tauri Cargo metadata 通过（由 GitHub Actions / 安装 Rust 后验证）
