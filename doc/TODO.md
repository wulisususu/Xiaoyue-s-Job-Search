# 未完成事项清单与路线图

> 更新时间：2026-09-21
>
> 本文件只保留当前仍需完成或继续加固的事项。已经进入当前功能基线并通过对应 CI/回归测试的能力集中列在文末，不再重复作为 TODO。

---

## P0：真实发布验证

### 1. Windows 真人 GUI smoke

**Status**：TODO

自动化已经覆盖 NSIS build、installer artifact、PyInstaller sidecar、fresh DB migration、health/auth smoke 和完整 Tauri link。仍需在真实 Windows 桌面人工确认最终交互体验。

- [ ] 从 CI artifact 安装 NSIS installer。
- [ ] 首次启动确认 sidecar 正常拉起。
- [ ] Job Radar 同步/浏览/验证入口。
- [ ] Resume Vault 导入。
- [ ] Draft Review → Profile SSOT。
- [ ] Browser Verify → Fill Plan → 回读验证。
- [ ] Moka ResumeVersion 显式上传。
- [ ] CRM 时间线和 resume linkage。
- [ ] 退出后确认不残留 Core 子进程。
- [ ] 卸载后确认程序目录清理。

**Acceptance**：普通 Windows 用户不安装 Python/Node/Rust 也能完成主链。

---

## P1：ATS Adapter 深化

### 2. 北森专项 adapter

**Status**：TODO

- [ ] 收集真实北森 apply-form fixtures。
- [ ] probe / page-state 识别。
- [ ] 原生字段路径或稳定语义提取。
- [ ] select / radio / date / repeatable section 行为验证。
- [ ] post-fill readback。
- [ ] 明确 unsupported controls，不用 generic fallback 冒充专项支持。

### 3. 飞书招聘专项 adapter

**Status**：TODO

- [ ] 收集真实飞书招聘 fixtures。
- [ ] 明确 form field identity。
- [ ] 控件语义映射。
- [ ] repeatable education/experience。
- [ ] readback / validation。
- [ ] popup / multi-step target 行为验证。

### 4. Hotjob 专项 adapter

**Status**：TODO

- [ ] 真实页面 probe。
- [ ] 稳定字段 identity。
- [ ] 控件行为与 readback。
- [ ] 登录态/多步骤页面状态。

### 5. Moka v2

**Status**：IN PROGRESS

Moka v1 已有 native path、indexed repeatable mapping 和受控 resume upload。仍需：

- [ ] cascading select。
- [ ] 没有 native path 的 repeatable section。
- [ ] `practiceInfo` 与本地 experience SSOT 的安全归类。
- [ ] customFields：只在有明确 schema/人工确认时支持。
- [ ] iframe form。
- [ ] 多步骤导航状态机。
- [ ] 其他附件的独立风险模型。

**明确不做**：自动点击最终提交。

---

## P1：Application CRM Phase 3

### 6. 更细的招聘阶段

**Status**：TODO

当前已有 ApplicationSession、合法状态机、resume_version_id 和 immutable ApplicationEvent。

继续增加：

- [ ] 笔试。
- [ ] 一面。
- [ ] 二面。
- [ ] HR 面。
- [ ] 体检 / 背调（如有）。
- [ ] Offer 接受/拒绝语义。

优先考虑事件模型，不把所有细阶段继续塞进一个 status enum。

### 7. Follow-up / Note

- [ ] 普通备注事件。
- [ ] `next_follow_up_at`。
- [ ] 待办视图。
- [ ] 逾期提醒。
- [ ] 面试时间/地点/会议链接。

### 8. 外部投递与重复检测

- [ ] 手动录入“已在官网/公众号/第三方完成”的申请。
- [ ] company/job/batch 级重复投递提示。
- [ ] external application id（可获得时）。
- [ ] 同岗位多轮/重新投递的显式 attempt 语义。

---

## P1：Dashboard / Product Surface

### 9. Dashboard 行动项

真实 KPI 已接入。继续增加：

- [ ] Browser Review Required 数量。
- [ ] Profile 待确认 Draft 数。
- [ ] Browser Fill FAILED / UNCERTAIN 待处理数。
- [ ] follow-up 到期。
- [ ] source quarantine 警告入口。

### 10. Saved Job / Bookmark

- [ ] 独立 saved-job/bookmark 模型。
- [ ] 不把收藏状态塞进 canonical Job。
- [ ] Dashboard 收藏统计只在模型落地后展示。

### 11. Settings 补齐非 AI 项

AI Provider 配置、Keyring、connectivity test、远程 HTTPS 已完成。

仍需：

- [ ] 本地数据目录只读展示。
- [ ] 打开数据目录。
- [ ] App / Core / DB schema version。
- [ ] 数据源状态汇总入口。
- [ ] cache/snapshot 占用信息。

---

## P2：E2E 与数据 fixtures

### 12. Browser E2E

- [ ] Playwright/可控 fixture：Browser Verify → Plan → Fill → readback。
- [ ] Moka native path fixture。
- [ ] Moka resume upload fixture。
- [ ] same-URL SPA step change → stale plan。
- [ ] popup/new-tab 不静默切 target。
- [ ] React re-render 后值回退 → FAILED。
- [ ] ambiguous option → 不自动选择。
- [ ] final submit 永不自动触发。

### 13. Source fixture replay

- [ ] 腾讯 SmartSheet 真实 payload fixture。
- [ ] completeness/quarantine replay。
- [ ] missing-vs-explicit-clear reconciliation fixture。
- [ ] WorkFind snapshot update fixture。

### 14. 性能基准

- [ ] 1k Job verification scheduler。
- [ ] 10k Job verification scheduler。
- [ ] URL verifier domain-concurrency benchmark。
- [ ] Dashboard aggregate query benchmark。

---

## P2：接口与工程化

### 15. OpenAPI generated types

- [ ] 固化 FastAPI OpenAPI schema。
- [ ] `openapi-typescript` 或等价方案生成前端 DTO。
- [ ] 手写 client 只保留业务 wrapper。
- [ ] CI 检测 generated types drift。

### 16. Dependency / supply-chain audit

- [ ] `npm audit` 策略。
- [ ] `pip-audit`。
- [ ] `cargo audit`。
- [ ] 明确 audit failure policy 与 allowlist。

### 17. Branch protection

- [ ] main required CI checks。
- [ ] 禁止未通过 required checks 的直接 merge。
- [ ] 视需要要求 review。

### 18. Snapshot / Vault retention

- [ ] WorkFind snapshot GC：current + 最近 N 个成功版本 + DB 引用版本。
- [ ] 腾讯 payload retention。
- [ ] failed/orphan temp cleanup。
- [ ] Browser Agent staging 异常退出 cleanup。
- [ ] UI 展示磁盘占用。
- [ ] 安全清理入口。

---

## P2：Release 文档

### 19. 安装与故障排查

- [ ] NSIS 安装说明。
- [ ] WebView2 缺失提示。
- [ ] Core sidecar 启动失败定位。
- [ ] logs 路径说明。
- [ ] AI Provider / Keyring 常见错误。
- [ ] Browser Agent Edge/CDP 常见错误。
- [ ] 数据备份与恢复说明。

---

## 已完成，不再作为 TODO

### Job / Source

- [x] Canonical Company / Job / Source。
- [x] WorkFind / 腾讯在线同步。
- [x] Last Known Good。
- [x] WorkFind immutable snapshot。
- [x] Tencent completeness quarantine。
- [x] quarantine 不再冒充 last-good/绿色健康状态。
- [x] missing-vs-explicit-clear Job reconciliation。
- [x] DB-side verification due filter。
- [x] server-side pagination / major N+1 cleanup。

### Verification / Security

- [x] URL verifier SSRF guard。
- [x] pinned-IP DNS rebinding / TOCTOU 防护。
- [x] redirect 每跳重新验证。
- [x] bounded reads / domain concurrency。
- [x] Browser Verify 解开 SPA/login/WAF deadlock。
- [x] fixed CDP target binding。
- [x] page revision / stale Fill Plan。
- [x] post-fill DOM readback。
- [x] final submit human gate。
- [x] local Core CSPRNG session token + auth middleware。
- [x] remote AI Provider HTTPS；HTTP 仅 localhost/loopback。

### Profile / Resume / AI

- [x] Immutable Resume Vault。
- [x] streaming upload / SHA-256 / PDF-DOCX guards。
- [x] scalar + structured Profile SSOT。
- [x] append-only revisions。
- [x] Draft review。
- [x] unified AI extraction contract。
- [x] AIExtractionRun audit / idempotency。
- [x] Keyring secret rotation。
- [x] Browser semantic mapping schema-only，实际 Profile 值仅 Core 本地解析。

### Browser Agent / ATS

- [x] verify/fill permission separation。
- [x] conservative value normalization。
- [x] ATS adapter registry。
- [x] Moka `moka_dom_v1`。
- [x] Moka native path / Ant-style id mapping。
- [x] indexed repeatable mapping。
- [x] controlled ResumeVersion upload。
- [x] browser FileList filename readback。
- [x] successful upload → CRM resume_version_id。
- [x] `RESUME_LINKED` ApplicationEvent。
- [x] arbitrary attachment / submit controls remain blocked。

### CRM / Dashboard

- [x] Application lifecycle state machine。
- [x] active attempt de-duplication。
- [x] resume_version_id。
- [x] immutable ApplicationEvent timeline。
- [x] Browser Agent status/event integration。
- [x] real Dashboard aggregate metrics。
- [x] data-driven empty states。

### Windows CI / Release

- [x] Web tests。
- [x] Core tests。
- [x] Alembic migration tests。
- [x] Web build。
- [x] PyInstaller sidecar build。
- [x] sidecar health/auth/migration smoke。
- [x] `cargo check`。
- [x] `cargo clippy -- -D warnings`。
- [x] `cargo test`。
- [x] full `tauri build`。
- [x] NSIS installer artifact upload。
