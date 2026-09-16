# Upstream Source Audit — 2026-09-16

本审计基于用户提供的三个完整 ZIP 快照，不依赖网络页面推断。

## 1. WorkFind

### 实际数据资产

supplied snapshot 中：

- `国企数据库.db`
  - `provinces`: 33
  - `companies`: 2060
  - `central_enterprises`: 100
- `国企数据库.json`: 以省/地区名为 key，value 为企业列表；单条核心字段目前为 `name`、`level`。
- `央企二级子公司.json`: 114 条，核心字段为 `parent`、`name`。
- `各省国企/`: 每省 Markdown + TXT 名录。
- `.reasonix/skills/workfind/references/company-sources.yaml`: 已验证/预计的招聘入口和备注。
- `.reasonix/skills/workfind/references/campus-calendar.md`: 校招时间线。

### 可直接借鉴

WorkFind 很适合作为 Company Registry 的 bootstrap source，但不应直接把其 SQLite 当成本项目生产数据库。

建议导入映射：

```text
WorkFind provinces/companies
        ↓
RawCompanyRecord
        ↓
Company Resolver
        ↓
companies / company_aliases / company_relations / company_sources
```

`company-sources.yaml` 的备注里同时混有已验证入口、当前开放/关闭状态、历史时间、预计开放时间、岗位方向和人工调查文本。因此不能整体塞进一个结构化 `status` 字段。Importer 第一版只安全提取 `campus`、公众号和原始备注，开放状态由后续 URL Verifier 单独判定。

### 风险

WorkFind 的“预计开放”不能升级成 `VERIFIED_OPEN`。来源文本可以保留，但业务状态必须由我们自己的验证器产生。

---

## 2. Xiaozhao Radar

### `jobs.json` 真实结构

顶层：

```json
{
  "updated": "2026-09-03",
  "count": 1598,
  "jobs": []
}
```

当前快照 `jobs` 数量与 `count` 均为 **1598**。

单条使用压缩键：

| Key | 含义 |
|---|---|
| `c` | company / 公司 |
| `p` | positions / 岗位文本 |
| `l` | location / 工作地点 |
| `e` | 扩展字段，当前多数为空 |
| `w` | wave / 招聘批次 |
| `d` | deadline / 截止描述 |
| `s` | source / 来源 |
| `t` | 类型 |
| `ind` | industry / 行业 |
| `u` | URL |

`SYNC_CORE.txt` 明确给出字段映射和数据源来自腾讯文档同步流程。

### 数据质量发现

当前 1598 条里：

- `u` 为空：**362 条**；
- Moka 链接很多（`app.mokahr.com` 当前快照 240 条）；
- Hotjob、微信公众号、51job、飞书招聘、国聘等多源混合；
- `s` 当前全部为 `校招信息聚合平台`，不能作为“官方来源”证据；
- `p` 经常是多个岗位类别合并文本，不一定是一岗一记录。

因此 Xiaozhao 更适合作为 **Recruitment Event / Discovery Feed**，不能直接生成 `VERIFIED_OPEN Job`。

建议流程：

```text
jobs.json
  ↓
XiaozhaoRawJob
  ↓
normalize compressed fields
  ↓
Company Resolver
  ↓
Job Candidate
  ↓
URL / ATS inspection
  ↓
JobSource + JobSnapshot
```

对于没有 URL 的 362 条，只允许进入“发现/待补入口”状态，不展示“开始申请”。

---

## 3. Offer Harvester

### Browser Session

`browser_session.py` 已实现一个很值得复用的模型：

- 独立 Chrome profile；
- 随机本机 loopback CDP port；
- `--remote-debugging-address=127.0.0.1`；
- session registry；
- PID + 进程创建时间 + CDP 三重校验，避免误连/误杀普通 Chrome；
- 自动化进程结束后可以保留浏览器供人工审核。

`browser.py` 同时支持 `launch_persistent_context()` 与独立 Chrome + `connect_over_cdp()` review 模式。这个设计比单纯“Playwright 启动一个临时浏览器”更符合本项目。

### Portal Adapter

`portals/base.py` 定义接口：

```text
is_logged_in()
login_hint()
open_job()
open_apply_form()
fill_form()
verify()
submit()
wait_receipt()
probe()
```

我们可以吸收接口思想，但把输入输出换成本项目自己的 Domain Schema。

当前快照已有站点适配器：generic、hotjob、tencent、boss、bilibili、bytedance、nowcoder、shixiseng、xiaohongshu、zhaopin。

注意：它当前并没有完整的 Moka / 北森 / 飞书专项 adapter，因此这些仍是我们后续重点。

### Generic Form Adapter

`portals/generic.py` 的安全边界非常值得保留：

- 未知 URL 不自动进入 generic，必须显式指定；
- 只接受申请表直达 URL；
- 不主动猜/点击“申请”按钮；
- 不自动提交；
- 附件只有在可见触发器明确写着“上传简历 / resume / CV”时才尝试上传；
- 多个不明确上传控件时停止猜测。

这证明我们的文件上传主链路不需要 OCR 猜坐标，可以优先基于 DOM + file chooser。

### Form Learning

`form_learning.py` 已经实现 label → profile path 的规则映射、`form_requirements`、selector metadata、occurrence 统计、缺失字段队列、sensitive 字段标识、已学习字段回填，并且不覆盖页面已有值。

其已有字段映射包括姓名、手机号、邮箱、学校、专业、学历、毕业时间、GPA、期望城市、薪资、自我介绍、照片等。

但本项目不能原样使用它的 Profile Schema，因为我们的 `CandidateProfile` 是 SSOT，并且 GREEN/YELLOW/RED 风险等级更严格。

### Sensitive Data

Offer Harvester 已明确禁止把身份证号写入 supplemental profile / DB / log。这一安全思想应保留。

我们的实现应进一步扩展到犯罪/处分声明、亲属/回避关系、真实性承诺和其他 RED 字段。

### Application Store

`application_store.py` 已存在：`applications`、`status_events`、`form_requirements`、`requirement_observations`、`source_runs`。

这证明它已经具备 CRM/表单学习雏形，但我们的数据库仍应自行建模，因为需要额外分离：

```text
companies
jobs
job_sources
job_snapshots
applications
application_events
resumes
resume_versions
candidate_profiles
answers
form_templates
form_fields
browser_sessions
```

### Job Identity

`job_identity.py` 已有 URL normalize、provider identity、source job id、`company + title + location` composite fingerprint。

这一部分适合直接参考 Job Deduper，但我们的优先级保持：

1. ATS job id
2. canonical apply URL
3. company + title + location + recruitment batch
4. semantic fingerprint

---

## 4. 三者不会冲突的最终边界

```text
WorkFind                    Xiaozhao Radar
   │                             │
Company facts                 Job feed
   │                             │
   └──────────┬──────────────────┘
              ↓
       Integration Layer
              ↓
 Company Resolver / Job Normalizer
              ↓
       Xiaoyue Domain DB
              ↓
Candidate Profile + Resume Vault
              ↓
          Fill Plan
              ↓
Browser Agent interface
              ↓
Offer Harvester patterns/adapters
              ↓
Recruitment Website
```

关键约束：WorkFind/Xiaozhao 不直接写最终业务表；Offer Harvester 不拥有本项目 Candidate Profile；第三方 Dashboard 不成为本项目 UI；上游源码快照不成为运行时 import path；所有第三方数据先进入 raw/staging 再 Normalize；最终提交保留人工确认门。

## 5. 下一阶段应实现的最小切片

建议下一开发切片只做数据侧，不碰 Browser Agent：

1. `Company` / `CompanyAlias` / `CompanyRelation` / `CompanySource` ORM；
2. `Job` / `JobSource` / `JobSnapshot` ORM；
3. WorkFind Importer；
4. Xiaozhao Importer；
5. Company Resolver；
6. Job Deduper；
7. API：公司列表、岗位列表、同步状态；
8. UI：岗位雷达先展示真实导入数据。

这样下一轮结束时，桌面端会从“空页面骨架”升级为真正能看到央国企和校招 Feed 的工作台。
