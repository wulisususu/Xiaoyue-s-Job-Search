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

## 上游参考源码

项目预留 `third_party/upstreams/` 作为专属上游参考区。完整源码快照放在 `third_party/upstreams/_local/`，默认不提交 Git；仓库只跟踪来源、SHA256、许可证说明和借鉴指南。

当前参考上游：

- WorkFind：央国企企业主库、集团关系、招聘来源与校招日历；
- Xiaozhao Radar：招聘事件流和岗位 Feed；
- Offer Harvester：Playwright Browser Agent、表单填写/上传、人工确认和投递追踪。

重新导入本地 ZIP 快照可使用 `scripts/import_upstreams.py`，详细边界见 `third_party/upstreams/ADOPTION_GUIDE.md`。

## 当前里程碑

MVP Foundation 只建立桌面壳、本地 Core API、SQLite、文件 Vault 根目录与测试基线。简历解析、招聘数据采集、Browser Agent、AI 填表将在后续里程碑接入。

## MVP Foundation 验收清单

- [x] Local API 提供 `/api/health`
- [x] SQLite 数据库写入 `XIAOYUE_DATA_DIR`
- [x] Local Vault 根目录自动创建
- [x] 桌面 UI 定义六个一级入口：首页、岗位雷达、投递中心、我的资料、简历库、设置
- [x] UI 接入本地 Core 健康状态
- [x] Core pytest 基线已建立
- [x] Web 测试通过（GitHub Actions Windows Runner）
- [x] Frontend production build 通过（GitHub Actions Windows Runner）
- [x] Tauri Cargo metadata 通过（GitHub Actions Windows Runner）
