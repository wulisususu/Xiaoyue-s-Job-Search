# Upstream Adoption Guide

## 原则

1. **上游快照不是运行时依赖。** `_local/` 只用于阅读、验证思路和对照实现。
2. **核心域模型由本项目定义。** Company、Job、Application、CandidateProfile、ResumeVersion 等实体不能直接沿用某个上游的私有结构。
3. **通过 Integration Layer 接入。** WorkFind/Xiaozhao 数据先 Normalize，再进入本项目数据库；Offer Harvester 的浏览器能力通过 Browser Agent 接口适配。
4. **保留许可证与来源。** 复制或改造实质代码前，必须保留对应 LICENSE/NOTICE 要求和原作者信息。
5. **不导入第三方个性化数据。** profile、cookie、登录态、生成简历、私有配置等一律不进入仓库。

## Offer Harvester

本地位置：`_local/offer-harvester/`

优先研究：

- `automation/apply_bot/browser.py`
- `automation/apply_bot/browser_session.py`
- `automation/apply_bot/apply_one.py`
- `automation/apply_bot/form_learning.py`
- `automation/apply_bot/materials.py`
- `automation/apply_bot/review_submit.py`
- `automation/apply_bot/application_store.py`
- `automation/apply_bot/job_identity.py`
- `automation/profile/profile.example.json`
- `.agents/skills/job-form-filler/`
- `.agents/skills/company-careers-search/`

准备借鉴的能力：

- Persistent Chrome / Playwright 会话管理；
- probe → analyze → fill → review → submit 的分段流程；
- 通用表单与站点 Adapter 思路；
- 文件上传和材料选择；
- 最终提交人工确认门；
- 岗位 identity / 去重和 application store；
- 表单学习与失败原因记录。

不直接照搬：

- 它自己的候选人 Profile 作为本项目 SSOT；
- 它的 Dashboard 作为我们的产品 UI；
- 任何已经个性化的简历、profile、cookie、mail/notion 配置。

本项目最终边界：

```text
CandidateProfile / ResumeVault
           ↓
      FillPlan
           ↓
 BrowserAgent interface
           ↓
Offer-Harvester-derived adapters
           ↓
Recruitment Website
```

## WorkFind

本地位置：`_local/workfind/`

优先研究：

- `国企数据库.json`
- `国企数据库.db`
- `央企二级子公司.json`
- `央国企完整名录_2026.txt`
- `央国企名录_分省索引.txt`
- `各省国企/`
- `.reasonix/skills/workfind/SKILL.md`
- `.reasonix/skills/workfind/references/company-sources.yaml`
- `.reasonix/skills/workfind/references/campus-calendar.md`
- `查国企.js`

准备借鉴的能力：

- 央企/地方国企 Company Registry；
- 母集团—子公司关系；
- 公司别名、地区、行业归类；
- 招聘官网/公众号来源登记；
- 校招开放时间与预计时间；
- 地区/行业/岗位/已开放等筛选语义。

必须做的隔离：

- “历史推算开放时间”只能进入 `PREDICTED_OPEN/UPCOMING`，不能当成 `VERIFIED_OPEN`；
- WorkFind 数据进入本项目前必须经过 Company Resolver 和去重；
- 招聘入口必须进一步区分 `source_url / career_home_url / apply_url`。

## Xiaozhao Radar

本地位置：`_local/xiaozhao-radar/`

优先研究：

- `jobs.json`
- `manifest.json`
- `SYNC.md`
- `SYNC_CORE.txt`
- `sync_tencent_docs.py`
- `proxy.js`

准备借鉴的能力：

- 实时 Job Feed；
- 数据同步/更新策略；
- 招聘条目字段和来源追踪；
- 发布日期、招聘批次、企业/行业分类等 Feed 信息。

不作为核心实现：

- `index.html` / `xiaozhao-radar.html` 的展示层；
- `promo.mp4` 等宣传资源。

Xiaozhao 数据应该进入：

```text
Raw Feed
  ↓
Job Normalizer
  ↓
Company Resolver
  ↓
Job Deduper
  ↓
URL Verifier
  ↓
Jobs / JobSources / JobSnapshots
```

## 推荐开发顺序

1. WorkFind Importer + Company Resolver
2. Xiaozhao Importer + Job Normalizer/Deduper
3. Candidate Profile + Resume Vault
4. Offer Harvester Browser Session / Probe 能力
5. Generic Form Adapter
6. Resume Upload Manager
7. Moka / 北森 / 飞书 / Hotjob 专项 Adapter
8. Application CRM + Success Detector
