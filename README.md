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

## Job Radar Core

岗位雷达当前已经接入自己的标准数据层，而不是直接读取 WorkFind / Xiaozhao 的原始文件。

数据链路：

```text
WorkFind ──> Company Registry ─┐
                               ├─> Company Resolver ─> Canonical Jobs ─> Core API ─> 岗位雷达 UI
Xiaozhao ─> Recruitment Feed ──┘                    └─> Job Sources / Provenance
```

当前支持：

- WorkFind 企业、央企/地方国企身份和央企关系导入；
- Xiaozhao Radar `jobs.json` 导入；
- 公司名称/别名解析；
- URL + fingerprint 岗位去重；
- 上游原始数据来源留档；
- `/api/jobs` 查询与筛选；
- `/api/jobs/stats` 雷达统计；
- 桌面端岗位卡片、企业性质、入口状态和基础筛选。

### 导入本地上游数据

先使用 `scripts/import_upstreams.py` 将三个 ZIP 恢复到 `_local/`，然后执行：

```powershell
python .\scripts\import_job_sources.py `
  --workfind-db .\third_party\upstreams\_local\workfind\国企数据库.db `
  --workfind-relations .\third_party\upstreams\_local\workfind\央企二级子公司.json `
  --xiaozhao-jobs .\third_party\upstreams\_local\xiaozhao-radar\jobs.json `
  --data-dir .\local-data\job-radar
```

当前用户提供快照的实际导入结果：

- WorkFind：2271 个企业 Source、111 条可明确建立的央企关系；
- Xiaozhao：1598 条 source rows 去重为 1486 个 canonical jobs；
- 其中 1125 个岗位有 URL 但仍是“入口待验证”；
- 361 个 canonical jobs 当前没有 URL。

**有 URL 不等于岗位已验证开放。** Xiaozhao 产生的 URL 当前统一保持 `DISCOVERED_URL_UNVERIFIED`，只有后续官方 URL Verifier 确认后才能升级为 `VERIFIED_OPEN` 并启用“开始申请”。完整状态和数据结构见 `doc/JOB_RADAR_DATA_MODEL.md`。

## 当前里程碑

### MVP Foundation

- [x] Local API 提供 `/api/health`
- [x] SQLite 数据库写入 `XIAOYUE_DATA_DIR`
- [x] Local Vault 根目录自动创建
- [x] 桌面 UI 定义六个一级入口：首页、岗位雷达、投递中心、我的资料、简历库、设置
- [x] UI 接入本地 Core 健康状态
- [x] Core pytest 基线已建立
- [x] Web 测试通过（GitHub Actions Windows Runner）
- [x] Frontend production build 通过（GitHub Actions Windows Runner）
- [x] Tauri Cargo metadata 通过（GitHub Actions Windows Runner）

### Job Radar Core

- [x] Canonical Company / Job / Source 数据模型
- [x] WorkFind Importer
- [x] Xiaozhao Importer
- [x] Company Resolver
- [x] Job Deduper
- [x] Job Radar API
- [x] 第一版岗位雷达 UI
- [x] 聚合 URL 默认保持“待验证”，不误标为可申请
- [ ] 官方 Apply URL Verifier
- [ ] ATS 类型识别
- [ ] Browser Agent 与“开始申请”联动

下一阶段优先实现 **Apply URL Verifier + ATS Detector**，让发现到的入口经过官方页面验证后，才进入 Browser Agent 自动投递链路。
