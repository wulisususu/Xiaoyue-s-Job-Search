# 未完成事项清单与路线图

> 更新时间：2026-09-17
> 范围：截至本日代码审查（commit `c3981b4`）仍未完成的工作。
> 已完成项（迁移、PRAGMA、快照不可变、SSRF 加固、分页、N+1 等）不在本清单内。

---

## 一、架构级改造（Browser Agent 之前必须完成）

### 1. Profile SSOT 升级为结构化集合

**现状**：Registry 是扁平字段（`education.school`、`education.major`…）+
`experience.summary` / `awards.summary` 一段文字。

**目标**：Scalar Fields + Structured Collections 双轨：

```
Education[]   ├ school / degree / major / start_date / end_date / GPA / ranking
Experience[]  ├ organization / role / start_date / end_date / location / bullets[]
Project[]
Award[]
Certificate[]
Language[]
Skill[]
```

**工作项**：

- [ ] 新数据表（或 JSON 结构化列）承载集合型经历，含迁移 `0002_*`
- [ ] `ProfileField / ProfileFieldRevision / ProfileDraftField` 三张表适配集合项
- [ ] `profile/registry.py`、`profile/service.py`、`profile/extraction.py` 升级
- [ ] AI 抽取 schema 从"字段字典"升级为"结构化数组"
- [ ] ProfilePage 前端从"字段列表"改为"分段经历编辑器"
- [ ] 迁移 + 数据回填测试（旧 summary 拆入新结构）

**不做后果**：Browser Agent 遇到"请分别填写三段经历"时只能临时让 AI 拆 summary，破坏 SSOT。

### 2. 统一 AI 抽象层

**现状**：两套漂移的契约并存：

- `ProfileExtractor` + `provider.complete()` + `ExtractionResult.fields`
- `OpenAICompatibleClient.extract_candidates()` → `candidates[]`

**工作项**：

- [ ] Task 3 开工前二选一，冻结唯一 Provider Contract
- [ ] 删除或合并被淘汰的一套
- [ ] 完成 Phase 3B Task 3～10：Resume → AI Extraction Run → Draft 持久化 → Review UI → 入库 SSOT 全链路

### 3. 桌面应用发布形态（Tauri sidecar）

**现状**：Tauri 主程序是空壳（`Builder::default().run()`）；Core API 靠
`scripts/dev.ps1` 手动起 uvicorn；前端写死 `http://127.0.0.1:8765`；
`bundle.active = false`。

**工作项**：

- [ ] 选定方案：Tauri sidecar 捆绑 Python 运行时 / portable venv / 核心迁 Rust
- [ ] Tauri 启动时拉起 Core，分配随机可用端口
- [ ] 前端通过 Tauri command 动态发现 Core 地址，去掉硬编码
- [ ] `bundle.active = true` + 安装器构建
- [ ] 双击 exe 全链路手工验收

### 4. 本机 API 认证（session token）

**现状**：Core API 只靠监听 `127.0.0.1`，无应用层认证。

**工作项**：

- [ ] Tauri 启动 Core 时生成随机 session secret
- [ ] Core 全路由校验 `Authorization: Bearer <local-session-token>`
- [ ] 前端所有 API 请求带 token（`coreClient.ts` 统一注入）
- [ ] 明确：本地 AI Provider 场景不允许复用招聘 URL verifier 的 guard 策略放行 localhost

**依赖**：第 3 项（token 的传递方式取决于谁启动 Core）。

---

## 二、产品层缺口

### 5. Dashboard 接真实数据

**现状**："今日新增 0 / 可申请 0 / 已收藏 0 / Offer 0" 全部硬编码，且提示
"还没有岗位和投递数据"——岗位雷达明明已有数据。

**工作项**：

- [ ] 今日新增 = `created_at` 在今日的 Job 数（可能需要后端补一个统计端点）
- [ ] 可申请 = `stats.verified_open`（`/api/jobs/stats` 已存在）
- [ ] 已收藏 / Offer：需要新的用户状态字段（收藏表、投递记录表），与投递中心一起设计
- [ ] 空状态文案改为真实条件判断

### 6. 投递中心

**现状**：纯 placeholder，明确等待 Browser Agent。

**工作项**：

- [ ] 设计投递记录模型（job_id、时间线状态：待投递/已投递/笔试/面试/offer/拒绝）
- [ ] Browser Agent 之外的**手动记录**模式可以先行（用户自己标记"已投递"）

### 7. 设置页

**现状**：placeholder；后端 Provider + keyring + API Key 轮换已就绪，前端未接。

**工作项**：

- [ ] Provider 配置表单（对接 `GET/PUT /api/ai/provider`）
- [ ] API Key 保存/删除 UI（对接 `PUT/DELETE /api/ai/provider/api-key`，注意不回显密钥）
- [ ] 数据源手动同步入口（现散落在岗位雷达页，可收敛至此）

---

## 三、已知技术债

### 8. 3 个测试在本机环境失败（非代码缺陷）

- `test_url_verifier.py::test_active_job_detail_with_apply_button_is_verified_apply`
- `test_verification_service.py::test_verified_apply_promotes_canonical_url_but_preserves_source_url`
- `test_verification_service.py::test_career_home_does_not_unlock_application`

**原因**：测试域名 `*.example.com` 在本地 DNS 解析失败，`validate_external_url`
在 fake transport 生效前就抛错。**修法**：参照
`test_verification_hardening.py` 的 `_no_dns` fixture，monkeypatch guard。
预计半小时，修完 CI 全绿。

### 9. DNS rebinding / TOCTOU

`validate_external_url` 校验时解析一次 DNS，urllib 连接时再解析一次，两次之间
可被切换到内网 IP。彻底修法是 pinned-IP 连接（连接到校验过的同一 IP）。
建议与 Browser Agent 阶段一起做。

### 10. Cargo.lock 缺失

`cargo metadata --no-deps` 不生成锁文件。首次 `cargo build` / `tauri build`
后**必须提交 Cargo.lock**。

### 11. CI 还缺的层

- [ ] `cargo check` / `cargo clippy`
- [ ] `tauri build` + installer 构建产物上传
- [ ] sidecar 集成测试（exe 启动 → Core 就绪 → health check）
- [ ] Playwright E2E（登录后核心流：同步 → 浏览 → 验证 → 上传简历）
- [ ] 真实数据源 contract fixture（腾讯文档 payload 样例回放）
- [ ] 依赖安全扫描：`npm audit` / `pip-audit` / `cargo audit`

---

## 建议动手顺序

```
① 修 3 个环境测试（半小时，CI 全绿）
② Profile 结构化（最大件，决定 AI 与 UI 的写法）
③ 统一 AI 抽象（紧随 ②）
④ Dashboard 真实数据 + 设置页 UI（独立，可与 ②③ 并行）
⑤ Tauri sidecar + session token（发布前置）
⑥ Browser Agent（以上全部就绪后）
```
