# 未完成事项清单与路线图

> 更新时间：2026-09-17
> 功能基线：`main@793f8545a354ad709fe18b00c4f19f526a7ddd79`
> 原则：本文件只保留**当前仍需完成或继续加固**的工作；已经落地并通过 CI 的事项集中放在文末，避免重复开发。

---

## P0：Browser Agent 前必须完成的架构基础

### 1. Tauri sidecar 发布闭环

**Status**：IN PROGRESS  
**Priority**：P0  
**Depends on**：CI Green  
**Blocks**：Release、真实用户安装

**已完成**：

- [x] Rust 端可寻找并启动 Core sidecar。
- [x] 随机可用 loopback 端口。
- [x] Tauri command 动态暴露 Core endpoint / session token。
- [x] 应用退出时关闭 sidecar。
- [x] 前端 Profile / Jobs / Resumes 等主链已具备动态 Core endpoint/auth 基础。
- [x] `Cargo.lock` 已提交。
- [x] CI 已实际执行完整 `tauri build`，Rust compile/link 可通过。

**仍需完成**：

- [ ] 确定 Python Core 发布方案，优先评估 PyInstaller `onedir`。
- [ ] 构建 `xiaoyue-core-api.exe`，验证 keyring / lxml / pypdf / python-docx / Alembic 等依赖完整。
- [ ] Tauri `externalBin` / resources 真正绑定 Core 可执行文件。
- [ ] `bundle.active = true`。
- [ ] 生成 Windows installer（NSIS/MSI 选定一个主渠道）。
- [ ] sidecar stdout/stderr 写入本地 rotating log，禁止 Release 永久吞掉。
- [ ] Core 启动失败时 UI 给出可诊断错误，而不是静默无后端。
- [ ] Fresh Windows smoke：安装 → 启动 → migration → health → Job Radar → Profile。

**Acceptance**：

- 用户不需要 Python / Node / Rust 环境。
- 安装后只需启动 Xiaoyue 即可使用 Core API。
- Tauri 退出后不遗留 Core 子进程。

---

## P1：产品主链继续补齐

### 2. Dashboard 接真实数据

**Status**：TODO  
**Priority**：P1

- [ ] 今日新增 = 本地今日 `created_at` Job 数。
- [ ] 可申请 = verified open 真实统计。
- [ ] 已投递 / 面试 / Offer = Application CRM 实时统计。
- [ ] 收藏使用独立 bookmark / saved-job 模型，不混进 canonical Job。
- [ ] 空状态基于真实数据。
- [ ] 首页提供待验证 / 待补 URL / 待跟进投递入口。

**Acceptance**：首页不存在硬编码 KPI。

---

### 3. Application CRM Phase 2

**Status**：IN PROGRESS  
**Priority**：P1

**已完成**：

- [x] `ApplicationSession` 第一版数据链。
- [x] “开始申请”可以创建记录并打开入口。
- [x] 投递中心展示记录并可手动修改状态。
- [x] 已有 `OPENED / IN_PROGRESS / SUBMITTED / INTERVIEWING / OFFER / REJECTED / ABANDONED`。

**仍需完成**：

- [ ] 加入 `resume_version_id`，明确每次投递使用哪份简历。
- [ ] 增加 Application Event Timeline，不只依赖最终 status。
- [ ] 增加笔试 / 一面 / 二面 / HR 面等阶段事件。
- [ ] 增加备注、下一步、跟进日期。
- [ ] 增加重复投递检测（同 company/job/batch）。
- [ ] 支持手动创建“已在外部投递”的记录。
- [ ] Browser Agent 完成后写入同一 CRM，不新建第二套申请记录。

**Acceptance**：手工投递和 Browser Agent 投递共用同一 Application SSOT。

---

### 4. 设置页

**Status**：TODO  
**Priority**：P1

- [ ] Provider 配置表单，对接 `GET/PUT /api/ai/provider`。
- [ ] API Key 保存 / 删除，对接 `PUT/DELETE /api/ai/provider/api-key`，不回显明文。
- [ ] Provider connectivity test。
- [ ] 数据源状态 / 手动同步入口。
- [ ] 本地数据目录只读展示 + 打开目录。
- [ ] App / Core / DB schema version 展示。

---

## P1：仍需解决的业务一致性问题

### 5. Canonical Job 字段清空语义

**Status**：TODO  
**Priority**：P1

`_merge_job_fields()` 需要明确区分 `MISSING` 与“上游明确清空”，否则旧 deadline/location 等值可能永久残留。

- [ ] `MISSING` = 不更新。
- [ ] `""` / `null` 按 source contract 表示显式清空。
- [ ] 为 title / location / industry / batch / deadline 增加 reconciliation tests。

---

## P2：工程化与发布质量

### 6. CI / Release pipeline 补齐

**Status**：IN PROGRESS  
**Priority**：P2

**已完成**：

- [x] npm / Python / Cargo lock。
- [x] Web tests / Core tests / migration tests。
- [x] Web build / Cargo metadata / `cargo check`。
- [x] CI 完整 `tauri build`。

**仍需完成**：

- [ ] `cargo clippy`。
- [ ] `cargo test`（Rust 层有可测逻辑后）。
- [ ] installer artifact 上传。
- [ ] sidecar integration test：exe 启动 → Core ready → authenticated call → shutdown。
- [ ] Playwright E2E：同步 → 浏览 → 验证 → 上传简历 → Draft Review → 开始申请。
- [ ] 腾讯文档真实 payload fixture 回放。
- [ ] `npm audit` / `pip-audit` / `cargo audit`。
- [ ] main branch required checks / protection。
- [ ] 1k / 10k Job verification scheduler benchmark。

---

### 7. OpenAPI 前后端契约生成

**Status**：TODO  
**Priority**：P2

- [ ] 固化 FastAPI OpenAPI schema。
- [ ] 使用 `openapi-typescript` 或等价方案生成前端 DTO。
- [ ] 手写接口只保留业务 wrapper。
- [ ] CI 检测 generated types 是否过期。

---

### 8. Snapshot / Vault retention policy

**Status**：TODO  
**Priority**：P2

- [ ] WorkFind immutable snapshot GC：保留 current + 最近 N 个成功版本 + 被 DB 引用版本。
- [ ] 腾讯 payload snapshot retention。
- [ ] orphan temp / failed upload cleanup policy。
- [ ] UI 展示缓存/数据占用并支持安全清理。
- [ ] 如果未来出现多 Core 进程，再把 source sync 的进程内 single-flight 升级为持久 lease。

---

### 9. README / 运行时文档同步

**Status**：IN PROGRESS  
**Priority**：P2

- [x] README 已修正部分数据目录 / 当前 Phase 状态。
- [x] 更新 Profile Structured Collections / Draft Review / 统一 AI 提取契约当前状态。
- [ ] 更新 Tauri sidecar 打包状态。
- [ ] 写 Release 安装 / 故障排查章节。
- [ ] 每次完成架构项后同步 TODO 功能基线。

---

## Browser Agent 开工门槛

- [x] main CI 全绿。
- [x] Profile Structured Collections 已落地。
- [x] AI Provider / Extraction Contract 已冻结并完成 run audit / idempotency。
- [x] Application CRM SSOT 已确定。
- [x] session token 使用 CSPRNG 并完成 auth tests。
- [x] DNS rebinding / TOCTOU 已通过 pinned-IP 方案关闭。
- [ ] Browser Agent 只读 confirmed Profile SSOT，不直接读取未经确认的 Draft。
- [ ] 每次最终提交前都有人类确认 gate。
- [ ] Browser Agent 投递结果写入现有 Application CRM。

---

## 建议执行顺序

```text
① Tauri sidecar 打包 / installer 闭环
   ↓
② Application CRM Phase 2 + Dashboard + Settings
   ↓
③ Browser Agent（confirmed Profile SSOT + human-confirm gate）
   ↓
④ Release hardening / E2E / installer smoke / dependency audit
```

---

## 最近完成（不再作为 TODO）

以下事项已经在当前功能基线落地，并经过 CI 或对应回归测试验证：

- [x] Session token 硬化：OS CSPRNG 生成 256-bit token（Windows BCryptGenRandom），只存两侧进程内存与 Authorization 头，绝不落 SQLite/log（含 token-不落库回归断言）。
- [x] Session auth E2E：无 token / 错 token → 401、正确 token → 200、health 豁免、foreign origin 拒绝、逐路由防绕过断言（未来 Browser Agent 高权限 router 天然被 middleware 覆盖）。
- [x] Core clients 审计：全部 client 统一经 `coreRuntime()` 动态端点 + `authHeaders()` wrapper，修复 resumesClient 硬编码端点且不带 token 的缺口。
- [x] CI 增加 `cargo test`（Rust 层 token 单测起）。
- [x] 统一 AI Provider / Extraction Contract：唯一 `ProfileExtractionProvider` 契约（`metadata()` + `extract() → ProfileExtractionBundle`）；`ProfileExtractor/provider.complete()` 与 `OpenAICompatibleClient.extract_candidates()` 双轨实现已删除。
- [x] `AIExtractionRun` 持久化（`0009_ai_extraction_runs` migration）：provider / model / prompt_version / schema_version / status / input_hash / error；provider 失败也落 FAILED run 而不是静默丢弃。
- [x] scalar / collection Draft 均关联 `extraction_run_id` + `candidate_fingerprint`，同一 run 重放不产生重复候选（partial unique index 硬约束）。
- [x] `Resume → AIExtractionRun → Draft → Review → Profile SSOT` 唯一正式链路；`POST / GET /api/ai/extraction-runs` 已落地，deterministic 导入链路走同一 orchestration。
- [x] Provider 边界：输入/输出长度上限、timeout、坏 JSON / 空响应 → `ProviderResponseError`，网络 / HTTP 错误 → `ProviderRequestError`，部分非法候选单项丢弃、合法候选保留；OpenAI / DeepSeek / Qwen 切换只改 `AIProviderConfig`。
- [x] Windows CI heredoc 问题修复；migration smoke 统一进入 pytest。
- [x] main CI 实际执行并通过 Web / Core / migration / Web build / Cargo metadata / `cargo check` / `tauri build`。
- [x] Alembic 为生产 schema source-of-truth；当前 migration chain 已扩展至 Profile Collections / Collection Drafts。
- [x] migration-built schema 与 ORM metadata drift guard。
- [x] SQLite foreign_keys / WAL / busy_timeout。
- [x] Profile Structured Collections：Education / Experience / Project / Award / Certificate / Language / Skill。
- [x] Collection CRUD / reorder / source / confidence / confirmed。
- [x] Collection revision history；删除 live item 后仍保留稳定 audit item id。
- [x] Collection Draft 单项 accept / reject，accept 与 SSOT revision 同事务。
- [x] ProfilePage 分段结构化编辑器 + 结构化候选审核 UI。
- [x] 旧 scalar Profile 字段继续保留，collection migrations 不丢旧数据。
- [x] DNS rebinding / TOCTOU pinned-IP：resolve once、校验全部地址、连接固定 IP、保留 Host/TLS SNI、redirect 每跳重新 pin。
- [x] Verification 状态保护：ACCESS_BLOCKED / LOGIN_REQUIRED / REQUIRES_BROWSER 不再直接破坏已验证业务状态。
- [x] Verification scheduler 使用 `jobs.next_verification_at` 做 DB 侧 due filter，去除原 N+1 路径。
- [x] Resume 真流式 temp-file ingest + incremental SHA-256 + ZIP bomb guards。
- [x] Source Sync 进程内 per-source single-flight。
- [x] Job identity 不再把 generic careers homepage 当 job-detail 强唯一身份。
- [x] WorkFind content-addressed immutable snapshots + atomic current pointer。
- [x] Tencent feed completeness gate / QUARANTINED mass-tombstone guard。
- [x] Canonical URL candidate → verify → promote 流程。
- [x] Company Resolver 三态：RESOLVED / AMBIGUOUS / NOT_FOUND。
- [x] URL verifier redirect-chain SSRF guard / SPA shell classification / bounded concurrency。
- [x] Job Radar server-side pagination。
- [x] `GET /api/jobs` 主要 N+1 已消除。
- [x] Resume Vault + scalar Profile SSOT + Draft Review 基线。
- [x] AI Provider config + keyring secret rotation 后端基线。
- [x] Application CRM 第一版 + “开始申请”手动入口记录。
- [x] Tauri sidecar 启动 / 动态端口 / endpoint command / 退出清理基础。
- [x] Local API Bearer session-token middleware + loopback Host/Origin 校验基础。
