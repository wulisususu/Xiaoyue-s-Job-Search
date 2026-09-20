# Xiaoyue's Job Search

面向央国企/校招求职的本地优先 Windows 桌面工作台。

它把岗位发现、招聘入口验证、个人资料 SSOT、不可变简历版本、AI 提取、Browser Agent 和投递 CRM 放在同一条可审计链路里，而不是把“抓岗位”“自动填表”“投递记录”做成彼此独立的脚本。

## 当前能力

### Job Radar

```text
WorkFind ──> Company Registry ─┐
                               ├─> Company Resolver ─> Canonical Jobs ─> Core API ─> Job Radar
Tencent / Xiaozhao Feed ───────┘                    └─> Job Sources / Provenance
```

已支持：

- WorkFind 企业、央企/地方国企身份与央企关系导入/同步；
- 腾讯 SmartSheet / Xiaozhao 招聘 Feed；
- Canonical Company / Job / Source 数据模型；
- 公司名称与别名解析；
- URL + fingerprint 岗位去重；
- server-side pagination 与岗位统计；
- Source Sync Run、不可变 WorkFind snapshot、Last Known Good；
- 腾讯 Feed 完整性 quarantine，异常骤减不会批量把岗位误标 stale；
- canonical Job 字段区分“上游缺失”和“上游明确清空”，避免 deadline/location 等旧值永久残留。

### Career URL Verification

招聘 URL 不因“存在一个链接”就被当成可申请。

当前流程：

```text
DISCOVERED_URL_UNVERIFIED
        │
        ├─ static verifier confirms apply page ───────────────┐
        │                                                     ↓
        └─ SPA / login / WAF / browser-required ─> Browser Verify
                                                              ↓
                                                        VERIFIED_OPEN
```

验证层包含：

- 只允许 http/https；
- DNS resolve-once + 全地址校验；
- 非公网/private/loopback/link-local/reserved/metadata 地址拒绝；
- pinned-IP 连接，保留原 Host / TLS SNI / 证书校验；
- redirect 每跳重新校验；
- bounded response reads；
- ATS 线索识别；
- URL observation、redirect chain、证据、fingerprint 留档；
- Rediscovery Candidate 必须先验证，不能直接覆盖 canonical URL；
- Browser Verify 模式只读页面，不允许填写/上传/提交。

## Profile SSOT + Immutable Resume Vault

Resume 是导入来源，不是运行时真相；Browser Agent 只读取人工确认后的 Profile SSOT。

```text
PDF / DOCX
    ↓
Immutable Resume Vault
    ↓
text extraction
    ↓
AI / deterministic extraction
    ↓
PENDING Drafts
    ↓ human accept / reject
Confirmed Profile SSOT
    ↓
ATS Mapping / Browser Agent
```

当前支持：

- PDF / DOCX；单文件最大 50 MiB；
- 流式上传、incremental SHA-256；
- 内容寻址不可变版本；
- PDF signature/open 校验；
- DOCX ZIP member / expanded-size / compression-ratio / required-member / CRC 校验；
- PDF 文本层与 DOCX 段落/表格提取；
- 无可用文本层的 PDF 标记为 `OCR_REQUIRED`，不伪造 OCR 结果；
- scalar Profile + Education / Experience / Project / Award / Certificate / Language / Skill collections；
- Draft accept/reject；
- append-only Profile revision history；
- sensitive Profile 值使用系统凭据存储引用，不把明文敏感值落普通 SQLite API 输出。

## Unified AI Provider / Extraction

AI Provider 使用统一 OpenAI-compatible 配置层。

已支持：

- Provider preset + custom Base URL / model；
- API Key 保存、轮换、删除；
- API Key 存系统 credential store，不回显明文；
- 远程 Provider 强制 HTTPS；
- HTTP 只允许 localhost / loopback 本机服务；
- Provider connectivity test；
- `AIExtractionRun` audit；
- prompt/schema/provider/model/input hash 持久化；
- Draft 幂等；
- input/output bounds、timeout、HTTP/network/bad-JSON 错误分类；
- 部分非法 AI 候选可以单项丢弃，不让整个合法结果一起失败。

正式链路：

```text
Resume → AIExtractionRun → validated PENDING Drafts → Review → Profile SSOT
```

## Browser Agent

Browser Agent 不是“自动提交机器人”。它的职责是识别页面、生成可解释 Fill Plan、等待用户确认、写入并验证结果；最终提交始终由用户本人完成。

### 安全边界

- `verify` 与 `fill` 两种模式分离；
- 未静态验证的 SPA/login/WAF 页面可以进入只读 Browser Verify；
- Fill 模式只允许 `VERIFIED_OPEN` Job；
- Browser session 绑定固定 CDP target，不静默切到新弹窗/新 tab；
- Fill Plan 绑定 page revision；页面/步骤变化后旧 plan 失效；
- AI semantic mapping 只看到字段 schema/path，不发送 Profile 实际值；
- Profile 实际值由 Core 本地解析；
- 高风险/需确认字段不默认自动勾选；
- password / submit / arbitrary file 等控件阻断；
- 填写后重新读取 DOM 值并输出 `VERIFIED / FAILED / UNCERTAIN`；
- 没有任何代码路径自动点击最终提交。

### ATS Adapter

Browser Agent 有独立 adapter registry，并复用 verifier 的 ATS 身份识别。

当前支持程度：

| ATS | 当前实现 |
| --- | --- |
| Moka | `moka_dom_v1` 专项 adapter |
| 北森 | `generic_dom` |
| 飞书招聘 | `generic_dom` |
| Hotjob | `generic_dom` |
| 其他站点 | generic fallback |

Moka v1 已支持：

- `basicInfo` 原生字段路径；
- indexed education / experience / project / language / award 映射；
- React / Ant Design 风格 DOM id 路径；
- 重复经历按原生 index 精确绑定，不依赖 DOM 出现顺序；
- 显式 Resume Vault 版本选择；
- 只允许识别为 Moka 原生 `resume` 的 file input；
- `DOM.setFileInputFiles` 后从浏览器 FileList 回读文件名；
- 上传成功后把实际 ResumeVersion 写回 Application CRM；
- `RESUME_LINKED` 不可变事件；
- session 结束清理 staging 文件。

Moka v1 当前仍需人工处理：

- 其他附件；
- 级联选择器；
- 没有原生 path 的重复区块；
- `practiceInfo` 的实习/工作归类；
- Moka custom fields；
- iframe 表单；
- 多步骤自动导航；
- 最终提交。

## Application CRM

手动申请和 Browser Agent 共用同一 `ApplicationSession` SSOT。

当前支持：

- `OPENED / IN_PROGRESS / SUBMITTED / INTERVIEWING / OFFER / REJECTED / ABANDONED`；
- 后端合法状态机，非法倒退返回冲突；
- 活跃 attempt 去重；
- `resume_version_id`；
- immutable `ApplicationEvent` timeline；
- Browser Agent 开始填写会产生状态事件；
- Browser Agent 简历上传成功会绑定实际 ResumeVersion 并产生 `RESUME_LINKED`；
- 桌面端只展示后端允许的下一状态；
- 时间线按需读取。

## Dashboard

Dashboard 已使用 Core 实时聚合，不再显示硬编码 0。

当前 KPI：

- 今日新增岗位；
- 可申请岗位；
- 央企岗位；
- 岗位总数；
- 填写中；
- 已投递；
- 面试中；
- Offer。

空状态也基于真实数据决定下一步动作。

## 本地安全模型

### Local Core API

Tauri 每次启动使用 OS CSPRNG 生成一次性 session token：

- token 只存在于 shell / Core 进程内存和 Authorization header；
- 不写 SQLite、配置文件或普通日志；
- `/api/*`（health 除外）统一 Bearer 校验；
- Host / Origin 限制为本机信任边界；
- 前端 Core client 统一经动态 runtime endpoint + auth headers。

### External URL

招聘 URL verifier 的 SSRF / DNS rebinding 防线与本地 Provider 访问是两套独立策略，不互相豁免。

## Windows 发布

技术栈：

- Node.js 20+
- Python 3.11+
- Rust stable
- Tauri 2 + React + TypeScript
- FastAPI + SQLAlchemy + SQLite
- Microsoft Edge WebView2 Runtime

Core 通过 PyInstaller onedir 打包，并作为 Tauri NSIS resource 安装。

CI 当前执行：

- Web tests；
- Core tests；
- Alembic migration tests；
- Web production build；
- PyInstaller Core sidecar build；
- sidecar health/auth/migration smoke；
- `cargo check`；
- `cargo clippy -- -D warnings`；
- `cargo test`；
- 完整 `tauri build`；
- 上传生成的 Windows NSIS installer artifact（14 天 retention）。

## 本地开发（Windows PowerShell）

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".\services\core-api[dev]"
npm install
.\scripts\test.ps1
.\scripts\dev.ps1
```

默认本地数据目录：

```text
~/.xiaoyue-job-search
```

Windows 通常为：

```text
C:\Users\<user>\.xiaoyue-job-search
```

可通过 `XIAOYUE_DATA_DIR` 覆盖。

## 上游参考源码

`third_party/upstreams/` 只保存来源、hash、许可证说明与采用边界；本地完整快照放在被 Git 忽略的 `third_party/upstreams/_local/`。

参考项目：

- WorkFind；
- Xiaozhao Radar；
- Offer Harvester。

详细审计见：

- `third_party/upstreams/UPSTREAM_AUDIT.md`
- `third_party/upstreams/ADOPTION_GUIDE.md`

## 下一阶段

当前核心数据层、Browser Agent 安全基础、Application CRM、Moka v1 与 Windows 发布链已经形成闭环。

下一阶段优先级：

1. 北森 → 飞书招聘 → Hotjob 专项 adapter；
2. Moka 级联选择、重复区块与多步骤能力；
3. 更细的笔试/一面/二面/HR 面事件与 follow-up；
4. Playwright/真实 ATS E2E fixtures；
5. dependency audit、branch protection、OpenAPI generated types；
6. 真人 Windows GUI smoke 与 Release 故障排查文档。

详细未完成事项见 `doc/TODO.md`。
