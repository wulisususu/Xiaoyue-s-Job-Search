# 未完成事项清单与路线图

> 更新时间：2026-09-17
> 基线：`main@8314e55181abb5bd5e763de47705931d8acaedb5`
> 原则：本文件只记录**当前仍需完成或继续加固**的工作；已完成事项集中放在文末，避免把历史问题继续当成待办。

---

## P0：先恢复可信主干

### 1. 修复当前 Windows CI workflow

**Status**：TODO  
**Priority**：P0  
**Depends on**：无  
**Blocks**：后续所有架构改造、Release

**现状**：

- Web tests：已通过。
- Core tests：已通过（当前 122 tests）。
- 当前 `main` CI 仍为红灯，失败发生在 migration smoke step。
- `.github/workflows/ci.yml` 在 `windows-latest` / PowerShell 下使用了 Bash heredoc：`python - <<'PY'`，导致 PowerShell ParserError。

**工作项**：

- [ ] 删除 CI YAML 中重复维护的内联 Python migration smoke 脚本，优先统一到 `pytest`。
- [ ] 如果暂时保留 heredoc，则显式指定 `shell: bash`。
- [ ] 确保 fresh DB migration test 真正执行成功。
- [ ] 确保 historical DB migration test 真正执行成功。
- [ ] 确保 Web build、Cargo metadata、`cargo check` 不再因前序失败而被跳过。
- [ ] main CI 恢复全绿后再继续大规模功能开发。

**Acceptance**：

- `main` 最新 GitHub Actions = green。
- migration / web / core / cargo check 全部实际执行，而不是 skipped。

---

## P0：Browser Agent 前必须完成的架构基础

### 2. Profile SSOT 升级为结构化集合

**Status**：TODO  
**Priority**：P0  
**Depends on**：CI Green  
**Blocks**：AI Extraction v2、ATS Mapping、Browser Agent

**现状**：Registry 仍以扁平字段为主：

- `education.school / education.major / education.degree / education.graduation_date`
- `skills.summary`
- `experience.summary`
- `awards.summary`

这无法直接表达多段教育、实习、项目、奖项等网申真实结构。

**目标**：Scalar Fields + Structured Collections 双轨。

```text
Scalar Fields
├─ identity.*
├─ contact.*
├─ location.*
└─ job.*

Structured Collections
├─ Education[]
│  ├─ school / degree / major
│  ├─ start_date / end_date
│  └─ GPA / ranking
├─ Experience[]
│  ├─ organization / role / location
│  ├─ start_date / end_date
│  └─ bullets[]
├─ Project[]
├─ Award[]
├─ Certificate[]
├─ Language[]
└─ Skill[]
```

**数据层建议**：不要把全部经历塞进一个不可追踪的大 JSON 列。优先选择：

- typed collection tables；或
- `profile_collection_items` 统一表 + item type + typed JSON payload + stable item id。

必须支持单项 revision、单项 draft、排序、删除、来源和 AI confidence。

**工作项**：

- [ ] 新增 migration：`0005_profile_collections`。
- [ ] 设计稳定的 collection item identity。
- [ ] Structured Collection 支持增 / 删 / 改 / 排序。
- [ ] Collection item 支持 source / confidence / confirmed 状态。
- [ ] Collection item revision history 可追踪。
- [ ] Draft review 可以逐项接受 / 拒绝，而不是整段 summary 一次性覆盖。
- [ ] `profile/registry.py`、`profile/service.py`、`profile/extraction.py` 升级。
- [ ] ProfilePage 从字段列表升级成分段经历编辑器。
- [ ] 旧 `experience.summary / awards.summary` 保留兼容读取，禁止直接丢数据。
- [ ] 为旧数据提供可重复执行的数据回填 / migration test。

**Acceptance**：

- 可以独立维护 3 段教育、3 段经历、多个项目/奖项。
- 每一项都能独立接受 AI Draft，并进入 SSOT。
- Browser Agent 不需要临时解析 summary 才能填写重复 ATS 表单组。

---

### 3. 统一 AI Provider / Extraction Contract

**Status**：TODO  
**Priority**：P0  
**Depends on**：Profile Structured Collections schema 基本冻结  
**Blocks**：AI Resume Extraction、OCR 后处理、Browser Agent AI 辅助

**现状**：存在两套有漂移风险的契约：

- `ProfileExtractor` + `provider.complete()` + `ExtractionResult.fields`
- `OpenAICompatibleClient.extract_candidates()` → `candidates[]`

**工作项**：

- [ ] 冻结唯一 `ProfileExtractionProvider` Contract。
- [ ] 删除 / 合并淘汰的一套实现，禁止双轨长期共存。
- [ ] 输出 schema 同时覆盖 scalar fields + structured collections。
- [ ] Provider 输出永远只能进入 Draft，禁止直接写 Profile SSOT。
- [ ] AI Extraction Run 持久化：provider / model / prompt/schema version / resume version / created_at / error。
- [ ] Draft 幂等：同一 extraction run 重放不能重复插入相同候选。
- [ ] 完成 Resume → AI Extraction Run → Draft → Review → SSOT 全链路。
- [ ] 设置最大输入长度、输出长度、timeout、JSON schema validation、错误降级策略。

**Acceptance**：

- AI 层只有一个正式 Provider Contract。
- 不同 OpenAI-compatible endpoint 可以无业务层改动切换。
- 无论模型返回什么，未经人工确认都不能污染 SSOT。

---

### 4. Tauri sidecar 发布闭环

**Status**：IN PROGRESS  
**Priority**：P0  
**Depends on**：CI Green  
**Blocks**：Release、真实用户安装

**已完成**：

- [x] Rust 端可寻找并启动 Core sidecar。
- [x] 随机可用端口。
- [x] Tauri command 动态暴露 Core endpoint。
- [x] 应用退出时关闭 sidecar。
- [x] 前端已具备动态 Core endpoint 基础。
- [x] `Cargo.lock` 已提交。

**仍需完成**：

- [ ] 确定 Python Core 发布方案，优先评估 PyInstaller `onedir`，不要默认 `onefile`。
- [ ] 构建 `xiaoyue-core-api.exe`，验证 keyring / lxml / pypdf / python-docx / Alembic 等依赖完整。
- [ ] Tauri `externalBin` / resource 配置真正绑定 Core 可执行文件。
- [ ] `bundle.active = true`。
- [ ] 生成 Windows installer（NSIS/MSI 选定一个主渠道）。
- [ ] sidecar stdout/stderr 不再永久吞掉：Release 写入本地 rotating log。
- [ ] Core 启动失败时 Tauri UI 显示可诊断错误，而不是静默无后端。
- [ ] Fresh Windows machine smoke test：双击安装 → 启动 → migration → health → Job Radar。

**Acceptance**：

- 用户不需要 Python / Node / Rust 环境。
- 安装后只需启动 Xiaoyue 即可使用 Core API。
- Tauri 退出后不遗留 Core 子进程。

---

### 5. 本机 API session token 安全加固

**Status**：IN PROGRESS  
**Priority**：P0  
**Depends on**：Tauri sidecar  
**Blocks**：Browser Agent 高权限控制接口

**已完成**：

- [x] Tauri 每次启动生成 session token 并传给 Core。
- [x] Core 对 `/api/*`（health 除外）校验 `Authorization: Bearer ...`。
- [x] 前端具备统一注入 endpoint/token 的基础。

**仍需完成**：

- [ ] 当前时间戳 + PID token 改为 CSPRNG（OS RNG，至少 256-bit）。
- [ ] 明确 token 只存内存，不落 SQLite / log。
- [ ] 增加 session auth E2E：无 token / 错 token / 正确 token。
- [ ] 检查所有 Core clients 是否都经过统一 authenticated fetch wrapper。
- [ ] Browser Agent 新增高权限 route 时禁止绕过 auth middleware。
- [ ] 明确本地 AI Provider 访问 localhost 与招聘 URL verifier SSRF guard 是两套不同安全策略。

**Acceptance**：

- 任意非 Tauri 本地进程无法在不知道 token 的情况下调用敏感 API。
- token 每次启动变化，且不可预测。

---

## P1：产品主链继续补齐

### 6. Dashboard 接真实数据

**Status**：TODO  
**Priority**：P1

**工作项**：

- [ ] 今日新增 = `created_at` 在本地今日范围内的 Job 数。
- [ ] 可申请 = `stats.verified_open`。
- [ ] 已投递 / 面试 / Offer = Application CRM 实时统计。
- [ ] 收藏数需要独立 bookmark / saved-job 模型，不要混进 Job canonical 数据。
- [ ] 空状态基于真实数据判断。
- [ ] Dashboard 提供“需要处理”的入口：待验证 / 待补 URL / 待跟进投递。

**Acceptance**：所有首页数字均来自真实数据库，不存在硬编码 KPI。

---

### 7. Application CRM Phase 2

**Status**：IN PROGRESS  
**Priority**：P1

**已完成**：

- [x] `ApplicationSession / Application Record` 第一版数据链。
- [x] 岗位雷达“开始申请”可以创建记录并打开入口。
- [x] 投递中心可展示记录并手动修改状态。
- [x] 已有 `OPENED / IN_PROGRESS / SUBMITTED / INTERVIEWING / OFFER / REJECTED / ABANDONED` 基础状态。

**仍需完成**：

- [ ] 加入 `resume_version_id`，明确每次投递使用哪份简历。
- [ ] 增加 Application Event Timeline，而不是只依赖一个最终 status。
- [ ] 增加笔试 / 一面 / 二面 / HR 面等阶段事件。
- [ ] 增加备注、下一步、跟进日期。
- [ ] 增加重复投递检测（同一 company/job/batch）。
- [ ] 支持纯手动创建“我已经在外部投递过”的记录。
- [ ] Browser Agent 完成后写入同一套 CRM，不新建第二套记录系统。

**Acceptance**：无论手工投递还是未来 Browser Agent 投递，最终都落到同一 Application SSOT。

---

### 8. 设置页

**Status**：TODO  
**Priority**：P1

**工作项**：

- [ ] Provider 配置表单，对接 `GET/PUT /api/ai/provider`。
- [ ] API Key 保存 / 删除，对接 `PUT/DELETE /api/ai/provider/api-key`，绝不回显明文。
- [ ] Provider connectivity test。
- [ ] 数据源状态 / 手动同步入口可从岗位雷达迁移或复用。
- [ ] 本地数据目录只读展示 + 打开目录。
- [ ] App / Core / DB schema version 展示，方便诊断。

---

## P1：仍需解决的技术债与可靠性问题

### 9. DNS rebinding / TOCTOU

**Status**：TODO  
**Priority**：P1-HIGH  
**Blocks**：Browser Agent 访问任意外部招聘 URL

`validate_external_url()` 校验 DNS 后，HTTP client 建连时还会再次解析域名，存在 DNS rebinding / TOCTOU 窗口。

**工作项**：

- [ ] resolve once。
- [ ] 校验解析出的全部地址均满足外网安全约束。
- [ ] 连接固定到已校验 IP，同时保留原始 Host / TLS SNI。
- [ ] redirect 每一跳重新执行同一套 pinned-IP 流程。
- [ ] 增加 rebinding / IPv6 / metadata endpoint 回归测试。

---

### 10. Verification 状态机：ACCESS_BLOCKED 不应破坏业务状态

**Status**：TODO  
**Priority**：P1

**问题**：已 `VERIFIED_OPEN` 的岗位，如果临时出现 403 / 429 / WAF / login wall，不能简单降回 `DISCOVERED_URL_UNVERIFIED`。

**工作项**：

- [ ] 区分 Job lifecycle status 与 Verification transport/page status。
- [ ] `ACCESS_BLOCKED / LOGIN_REQUIRED / REQUIRES_BROWSER` 不直接否定已验证开放状态。
- [ ] 仅 `BROKEN / STALE` 在满足确认策略后触发 rediscovery。
- [ ] 增加连续失败阈值，避免一次临时网络错误改变业务状态。

---

### 11. Verification scheduler 去 N+1

**Status**：TODO  
**Priority**：P1

**现状**：`verify_due_jobs()` 先加载全部有 URL 的 Job，再逐 Job 查询 latest `UrlObservation` 判断是否到期。

**目标方案**：

- 优先增加 `jobs.next_verification_at`；或
- 用 latest observation 子查询一次完成 due filter。

**工作项**：

- [ ] DB 侧直接筛选 due jobs。
- [ ] 保留现有 per-host serialization + bounded concurrency。
- [ ] 增加 1k / 10k Job scheduler 性能测试。

**Acceptance**：取 50 个 due job 的 SQL 数量保持常数级。

---

### 12. Resume 真正流式写入 + 压缩包安全

**Status**：TODO  
**Priority**：P1

**现状**：上传目前虽然按 1 MiB chunk 读取，但仍 `chunks.append()` 后 `b"".join()`，50 MiB 文件依旧整体驻留内存。

**工作项**：

- [ ] `UploadFile` chunk → temp file。
- [ ] 上传时增量计算 SHA-256。
- [ ] 边写边限制最大 size。
- [ ] 完成格式 / magic validation 后 atomic move 到 content-addressed vault。
- [ ] DOCX 增加 ZIP member count / total uncompressed size / compression ratio 限制。
- [ ] crash 后 temp/orphan 清理仍需可恢复。

**Acceptance**：50 MiB 上传时不再保留“chunks + joined bytes”双份内存。

---

### 13. Source Sync single-flight / lease

**Status**：TODO  
**Priority**：P1

**工作项**：

- [ ] 同一 source 同一时间只允许一个 sync run。
- [ ] `SourceSyncRun` 增加 RUNNING / lease semantics，或至少先加进程内 per-source lock。
- [ ] 多窗口 / scheduler / 手工点击同时触发不会重复导入。
- [ ] crash 后 lease 可超时恢复。

---

### 14. Canonical Job 字段清空语义

**Status**：TODO  
**Priority**：P1

**问题**：`_merge_job_fields()` 当前只在 `value` truthy 时覆盖，因此上游明确把 deadline/location 等字段清空时，旧值会永久残留。

**工作项**：

- [ ] 明确区分 `MISSING` 与“字段明确为空”。
- [ ] `MISSING` = 不更新；`""` / `null`（按 source contract）= 显式清空。
- [ ] 为 title/location/industry/batch/deadline 建 reconciliation tests。

---

### 15. Job identity：通用招聘首页不能当 job-detail 唯一身份

**Status**：TODO  
**Priority**：P1

**问题**：多个岗位可能共享企业 careers homepage。单纯 URL 相同不一定代表同一岗位。

**目标优先级**：

```text
ATS stable job id
> verified job-detail URL
> company + title + location + batch
> generic careers URL 仅作为 source evidence
```

**工作项**：

- [ ] URL classifier 标记 generic career homepage vs job detail。
- [ ] generic careers URL 不参与强唯一去重。
- [ ] ATS stable id 可用时进入 canonical identity。
- [ ] 增加“同一 careers URL 下多个岗位”的回归测试。

---

## P2：工程化与发布质量

### 16. CI / Release pipeline 补齐

**Status**：IN PROGRESS  
**Priority**：P2

**已完成**：

- [x] npm lock / Python requirements lock。
- [x] `Cargo.lock`。
- [x] Web tests / Core tests。
- [x] `cargo check` 已写入 workflow（需先修 P0 CI 才能稳定实际跑到）。

**仍需完成**：

- [ ] `cargo clippy`。
- [ ] `cargo test`（如 Rust 层开始增加可测逻辑）。
- [ ] `tauri build`。
- [ ] installer artifact 上传。
- [ ] sidecar integration test：exe 启动 → Core ready → auth health/control call → shutdown。
- [ ] Playwright E2E：同步 → 浏览 → 验证 → 上传简历 → Profile Draft Review → 开始申请。
- [ ] 腾讯文档真实 payload contract fixture 回放。
- [ ] `npm audit` / `pip-audit` / `cargo audit`。
- [ ] main branch required checks / protection。

---

### 17. OpenAPI 前后端契约生成

**Status**：TODO  
**Priority**：P2

**工作项**：

- [ ] FastAPI OpenAPI schema 固化。
- [ ] 使用 `openapi-typescript` 或等价方案生成前端 DTO。
- [ ] 手写接口只保留业务 wrapper，不再复制 response type。
- [ ] CI 检测 generated types 是否过期。

---

### 18. Snapshot / Vault retention policy

**Status**：TODO  
**Priority**：P2

**工作项**：

- [ ] WorkFind immutable snapshot GC：保留 current + 最近 N 个成功版本 + 被 DB 引用版本。
- [ ] 腾讯 payload snapshot retention。
- [ ] orphan temp / failed upload cleanup policy。
- [ ] UI 显示缓存/数据占用并支持安全清理。

---

### 19. README / 运行时文档同步

**Status**：TODO  
**Priority**：P2

**工作项**：

- [ ] README 默认数据目录与代码保持一致。
- [ ] 更新当前 AI Phase 状态，不再写成尚未开始。
- [ ] 更新 Tauri sidecar 当前实现状态。
- [ ] 写 Release 安装 / 故障排查章节。
- [ ] TODO 每次完成架构项后同步更新基线 commit。

---

## Browser Agent 开工门槛

Browser Agent **不要仅因为 Playwright 能跑就开工**。至少满足：

- [ ] main CI 全绿。
- [ ] Profile Structured Collections 已落地。
- [ ] AI Provider Contract 已冻结。
- [ ] Application CRM SSOT 已确定。
- [ ] session token 使用 CSPRNG 并完成 auth tests。
- [ ] DNS rebinding / TOCTOU 有明确解决方案并落地到 Agent 网络边界。
- [ ] Browser Agent 只读 confirmed Profile SSOT，不直接读取未经确认的 AI Draft。
- [ ] 每次最终提交前都有人类确认 gate。
- [ ] Browser Agent 的投递结果写入现有 Application CRM。

---

## 建议执行顺序

```text
① P0 修 CI workflow，main 恢复全绿
   ↓
② Profile Structured Collections（0005）
   ↓
③ 统一 AI Provider / Extraction Contract
   ↓
④ Resume streaming + Verification 状态机 / scheduler
   ↓
⑤ 完成 Tauri sidecar 打包、CSPRNG session token、installer
   ↓
⑥ Dashboard + Settings + Application CRM Phase 2
   ↓
⑦ DNS pinned-IP / Browser Agent 安全边界
   ↓
⑧ Browser Agent
   ↓
⑨ Release hardening / E2E / installer smoke / dependency audit
```

---

## 最近完成（不再作为 TODO）

以下事项已经在当前 `main` 落地，保留在此仅用于避免重复开发：

- [x] Alembic 成为生产 schema source-of-truth。
- [x] `0001_initial_schema → 0002_job_source_lifecycle → 0003_application_sessions → 0004_url_candidates` migration chain。
- [x] migration-built schema 与 ORM metadata drift guard。
- [x] SQLite foreign_keys / WAL / busy_timeout。
- [x] WorkFind content-addressed immutable snapshots + atomic current pointer。
- [x] Tencent feed completeness gate / QUARANTINED mass-tombstone guard。
- [x] Canonical URL candidate → verify → promote 流程。
- [x] Company Resolver 三态：RESOLVED / AMBIGUOUS / NOT_FOUND，歧义不再制造新 Company。
- [x] URL verifier redirect-chain SSRF guard / SPA shell classification / bounded concurrency。
- [x] Job Radar server-side pagination。
- [x] `GET /api/jobs` 主要 N+1 已消除。
- [x] Resume Vault + Profile SSOT + Draft Review 基线。
- [x] AI Provider config + keyring secret rotation 后端基线。
- [x] Application CRM 第一版 + “开始申请”手动入口记录。
- [x] Tauri sidecar 启动/动态端口/endpoint command/退出清理基础。
- [x] Local API Bearer session-token middleware 基础。
- [x] 原先 3 个 verifier fake-domain 测试问题已修复；当前 Core tests 可通过。
- [x] `Cargo.lock` 已提交。
