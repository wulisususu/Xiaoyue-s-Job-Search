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

默认本地数据目录为 `~/.xiaoyue-job-search`（Windows 上即 `C:\Users\<user>\.xiaoyue-job-search`）。可通过环境变量 `XIAOYUE_DATA_DIR` 覆盖。

## 上游参考源码

项目预留 `third_party/upstreams/` 作为专属上游参考区。完整源码快照放在 `third_party/upstreams/_local/`，默认不提交 Git；仓库只跟踪来源、SHA256、许可证说明和借鉴指南。

当前参考上游：

- WorkFind：央国企企业主库、集团关系、招聘来源与校招日历；
- Xiaozhao Radar：招聘事件流和岗位 Feed；
- Offer Harvester：Playwright Browser Agent、表单填写/上传、人工确认和投递追踪。

重新导入本地 ZIP 快照可使用 `scripts/import_upstreams.py`，详细边界见 `third_party/upstreams/ADOPTION_GUIDE.md`。

## Job Radar Core

岗位雷达已经接入自己的标准数据层，而不是直接把上游文件当成最终事实。

数据链路：

```text
WorkFind ──> Company Registry ─┐
                               ├─> Company Resolver ─> Canonical Jobs ─> Core API ─> 岗位雷达 UI
Xiaozhao ─> Recruitment Feed ──┘                    └─> Job Sources / Provenance
```

当前支持：

- WorkFind 企业、央企/地方国企身份和央企关系导入；
- Xiaozhao Radar Feed 导入；
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

用户提供快照的基线导入结果：

- WorkFind：2271 个企业 Source、111 条可明确建立的央企关系；
- Xiaozhao：1598 条 source rows 去重为 1486 个 canonical jobs；
- 其中 1125 个岗位有 URL 但初始仍是“入口待验证”；
- 361 个 canonical jobs 初始没有 URL。

**有 URL 不等于岗位已验证开放。** 上游 URL 首先保持 `DISCOVERED_URL_UNVERIFIED`，只有验证器确认页面存在明确可申请入口后才升级为 `VERIFIED_OPEN` 并启用“开始申请”。完整状态和数据结构见 `doc/JOB_RADAR_DATA_MODEL.md`。

## Online Source & Career Verification Engine

岗位发现数据现在有独立的在线更新与真实性验证层，避免长期依赖某个静态 `jobs.json` 或已经过期的招聘地址。

当前支持：

- 直接读取腾讯 SmartSheet 公开数据，而不是把 Xiaozhao 仓库中的静态 JSON 当作长期运行时数据源；
- WorkFind 结构化数据在线同步；
- Source Sync Run 记录和 Last Known Good Snapshot；
- 腾讯文档 6 小时、WorkFind 24 小时的到期同步策略；同步失败 1 小时后可重试；
- 岗位入口只读 URL 验证、重定向解析和页面类型分类；
- Moka、北森、Hotjob、飞书招聘、51job、国聘、SuccessFactors 等 ATS 线索识别；
- 原始 URL、最终 URL、redirect chain、验证时间和页面证据留档；
- 失效入口只生成 Rediscovery Candidate，不未经验证覆盖 canonical URL；
- 只有 `VERIFIED_APPLY -> VERIFIED_OPEN` 才解锁未来 Browser Agent 的申请入口。

## Profile SSOT + Immutable Resume Vault（Phase 3A）

候选人信息已经从“简历文件”与“可信在线资料”两层分开：

```text
PDF / DOCX
    ↓
Immutable Resume Vault
    ↓
文本层解析
    ↓
Extraction Drafts（未确认）
    ↓ 人工接受 / 拒绝
Profile SSOT（confirmed=true）
    ↓
未来 ATS Mapping / Browser Agent
```

核心原则：**Resume 是导入来源，不是运行时真相；只有人工确认过的 Profile SSOT 才允许未来自动填表使用。**

当前支持：

- 桌面端导入 `.pdf` / `.docx` 简历；
- 单文件最大 50 MiB；旧 `.doc` 明确拒绝；
- SHA-256 内容寻址和不可变 Resume Version；相同字节重复上传不会生成新版本；
- Vault 路径：`<XIAOYUE_DATA_DIR>/vault/resumes/<sha256>/original.<ext>`；API 不暴露本机 Vault 绝对路径；
- PDF 文本层优先提取、DOCX 段落/表格文本提取；
- 无可用文本层的 PDF 标记为 `OCR_REQUIRED`，Phase 3A 不伪造 OCR 结果；
- 当前 deterministic extractor 仅保守识别严格邮箱和中国大陆手机号；
- 简历解析结果只能形成 `PENDING` Draft，导入不会直接修改 Profile；
- Draft 可以显式接受或拒绝；接受后写入 confirmed Profile，拒绝不改变 Profile；
- Profile 支持手动创建/编辑；
- 每次 Profile 变化都追加 `profile_field_revisions`，保留来源、旧值、新值、置信度和时间；
- Core API 暴露服务端唯一 Field Registry，桌面端不复制一套字段定义；
- “简历库”页面展示版本、hash 前缀、文件大小、解析状态、待审核数和 OCR 状态；
- “我的资料”页面展示全部 Registry 字段、已确认来源以及待审核 Draft。

Phase 3A 明确**没有**引入网络 AI、OCR 引擎、Browser Agent、API Key 或 Credential Store。

详细设计：`docs/superpowers/specs/2026-09-16-profile-resume-vault-design.md`

实施计划：`docs/superpowers/plans/2026-09-16-profile-resume-vault.md`

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

### Online Source & Career Verification Engine

- [x] 腾讯 SmartSheet 在线同步
- [x] WorkFind 在线同步
- [x] Last Known Good Snapshot / Sync Run 历史
- [x] Apply URL Verifier
- [x] ATS Detector
- [x] URL 健康状态与验证证据
- [x] Rediscovery Candidate 安全门
- [x] 到期自动同步策略
- [ ] Browser Agent 与“开始申请”联动

### Profile SSOT + Resume Vault — Phase 3A

- [x] Canonical Profile Field Registry
- [x] Immutable Resume Vault
- [x] SHA-256 去重与不可变版本号
- [x] PDF / DOCX 文本解析
- [x] `OCR_REQUIRED` 状态
- [x] Conservative deterministic Draft extraction
- [x] Draft 接受 / 拒绝事务
- [x] 手动 Profile 编辑
- [x] Append-only Profile revision history
- [x] Resume / Profile Core API
- [x] 简历库 UI
- [x] Profile SSOT / Draft Review UI
- [x] Windows CI 覆盖 Web / Core / Build / Tauri metadata

### Unified AI Extraction Contract — Phase 3C

- [x] 唯一 `ProfileExtractionProvider` 契约：`metadata()` + `extract() → ProfileExtractionBundle`（scalar 候选 + structured collection 候选 + provider/model/prompt/schema 元数据）
- [x] `AIExtractionRun` 持久化（`0009_ai_extraction_runs` migration）：provider / model / prompt_version / schema_version / status / input_hash / error；失败也落 FAILED run
- [x] Draft 幂等：`extraction_run_id` + `candidate_fingerprint` partial unique index，同一 run 重放不产生重复候选
- [x] `POST / GET /api/ai/extraction-runs` 正式链路入口；deterministic 导入走同一 orchestration
- [x] Provider 边界：输入/输出长度上限、timeout、bad JSON / 空响应 / 网络 / HTTP 错误分类、部分非法候选单项丢弃
- [x] 删除 `ProfileExtractor + provider.complete()` 与 `OpenAICompatibleClient.extract_candidates()` 双轨实现

### 本地安全模型（两套互不重叠的策略）

1. **本机 API 信任边界（session token）**：token 由 Tauri shell 每次启动用 OS CSPRNG 生成（BCryptGenRandom，256-bit hex），只存在于两侧进程内存与 `Authorization: Bearer` 头中，绝不落入 SQLite、日志或磁盘；`/api/*`（health 除外）强制校验 Bearer + loopback Host/Origin。新增任何 router（包括未来的 Browser Agent 高权限路由）天然被 middleware 覆盖——存在回归测试逐路由断言。前端所有 Core client 统一经 `coreRuntime()` + `authHeaders()` wrapper。
2. **招聘 URL verifier SSRF guard**：core 主动出网抓取/验证招聘 URL 时走 pinned-IP 校验（resolve-once、逐地址校验、redirect 每跳重新 pin）。它与「本地 AI Provider 访问 localhost 出网」是两套独立安全策略，互不豁免。

## 当前状态与下一阶段

Phase 3C 已落地统一 AI 提取契约，session token 已硬化（OS CSPRNG + auth E2E + 全 client 统一 wrapper）。剩余工作见 `doc/TODO.md`，重点包括：

1. Tauri sidecar 打包（PyInstaller onedir）与安装器构建；
2. Application CRM Phase 2、Dashboard 真实数据与设置页；
3. Browser Agent：Job → Verify → Start Application → ApplicationSession → ATS Mapping → Human Confirm → Submit。

Browser Agent 自动填表继续在 Profile/Provider 数据底座稳定后接入。