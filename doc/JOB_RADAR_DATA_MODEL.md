# Job Radar Data Model

## 1. 目标

Job Radar 不直接把 WorkFind 或 Xiaozhao Radar 的文件当生产数据库，而是把它们视为 **可追溯的发现源（discovery sources）**。所有上游数据必须先进入 Integration Layer，再转换成 Xiaoyue 自己的 Company / Job / Source 域模型。

核心原则：

```text
Source Data != Truth
URL Exists != Verified Open
Company Name != Company Identity
Job Feed Row != Unique Job
```

因此，当前阶段宁可把状态保守标记为“待验证”，也不允许把聚合数据误判成“官网正在开放申请”。

---

## 2. 上游职责

### WorkFind

主要用于建立 Company Registry：

- 央企主表；
- 地方国企主表；
- 省份/地区；
- 企业层级；
- 央企与子公司关系；
- 公司别名与招聘来源参考。

WorkFind 数据进入：

```text
WorkFind SQLite / Relations JSON
            ↓
       WorkFind Importer
            ↓
companies
company_aliases
company_relations
company_sources
```

### Xiaozhao Radar

主要作为招聘事件流：

```text
jobs.json
  ↓
Xiaozhao Importer
  ↓
Company Resolver
  ↓
Job Deduper
  ↓
jobs + job_sources
```

其 `jobs.json` 压缩字段映射：

| 上游键 | 本项目字段 |
|---|---|
| `c` | company name |
| `p` | job title / position text |
| `l` | location |
| `w` | recruitment batch |
| `d` | deadline text |
| `ind` | industry |
| `t` | fallback category |
| `u` | source/apply URL candidate |

`p` 可能是多个岗位类别的聚合文本，所以当前阶段不强行拆成多个岗位，避免制造不存在的职位记录。

---

## 3. Company 模型

### `companies`

保存标准企业实体：

```text
id
name
normalized_name
ownership
province
level
created_at
updated_at
```

`ownership` 当前允许：

- `central_soe`：已由企业主库/关系解析确认的央企或央企关系企业；
- `local_soe`：已由 WorkFind 地方国企主库确认；
- `unknown`：招聘 Feed 中出现，但当前资料不足以确认企业性质。

`unknown` 不代表“不是国企”，只代表 **当前解析器没有足够证据确认**。

### `company_aliases`

一个 Company 可以对应多个来源名称，例如：

```text
中国移动通信集团有限公司
中国移动通信集团
中国移动
```

别名必须带 `source_name`，避免无法追溯是谁提供了这个映射。

### `company_relations`

当前关系类型主要是：

```text
subsidiary
```

关系必须明确指向两个 Company ID，不能只保存字符串。

WorkFind 当前 114 条央企关系中，真实全量导入建立 111 条。剩余 3 条属于上游 `中国航运 -> 国航 / 东航 / 南航` 的语义歧义，当前实现选择跳过，而不是猜测 parent company。

### `company_sources`

记录企业来自哪个上游以及上游主键：

```text
company_id
source_name
source_key
raw_json
```

用于幂等导入、审计和未来数据修复。

---

## 4. Company Resolver

解析步骤保持保守：

1. 企业名称 Unicode / 标点归一化；
2. 仅剥离法律形态后缀：
   - 股份有限公司
   - 有限责任公司
   - 有限公司
   - 公司
3. **保留“集团”**，因为它是主体名称的一部分；
4. 精确匹配 `normalized_name`；
5. 再匹配 `company_aliases`；
6. WorkFind 央企关系允许使用少量人工确认的 source alias → official name 映射；
7. 无唯一证据时不强绑，Xiaozhao 企业创建为 `unknown`。

例如：

```text
中国核工业集团有限公司
→ 中国核工业集团
```

而不是：

```text
中国核工业
```

---

## 5. Job 模型

### `jobs`

保存去重后的标准招聘事件：

```text
id
company_id
title
location
industry
recruitment_batch
deadline_text
apply_url
canonical_url
status
fingerprint
source_updated_at
created_at
updated_at
```

### `job_sources`

一个标准 Job 可以有多个来源记录：

```text
job_id
source_name
source_record_key
source_url
raw_json
first_seen_at
last_seen_at
```

因此 1598 条 Xiaozhao source rows 可以对应少于 1598 个 canonical Jobs。

---

## 6. Job 去重

当前优先级：

```text
1. canonical apply URL
2. company + title + location + recruitment_batch fingerprint
```

后续接入官方 ATS 后扩展成：

```text
1. ATS stable job ID
2. canonical apply URL
3. company + title + location + recruitment batch
4. semantic fingerprint
```

URL 标准化只移除明确的 tracking 参数；不会在未知站点上激进改写 URL。

---

## 7. 招聘状态

当前正式实现两种发现状态：

### `DISCOVERED_NO_URL`

含义：

- 招聘 Feed 中发现该记录；
- 当前没有可用 URL；
- 只能用于发现/筛选；
- UI 显示“待补申请入口”；
- 不允许点击“开始申请”。

### `DISCOVERED_URL_UNVERIFIED`

含义：

- Feed 提供了 URL；
- URL 已被保存和标准化；
- **尚未经过官方入口验证器确认**；
- UI 显示“入口待验证”；
- 可以点击“查看原始入口”；
- 不允许点击“开始申请”。

后续 URL Verifier 才能产生：

### `VERIFIED_OPEN`

预期要求至少满足：

1. URL 可访问；
2. 跳转链已解析；
3. 页面属于招聘/ATS 申请链路，而不是企业介绍页；
4. 能定位岗位详情或申请入口；
5. 页面没有明确显示岗位关闭；
6. 验证结果带时间戳和来源证据。

只有 `VERIFIED_OPEN` 才允许平台启用“开始申请”。

未来还会扩展：

```text
UPCOMING
UNKNOWN
CLOSED
```

但当前阶段不提前制造这些状态。

---

## 8. API

### `GET /api/jobs`

支持：

```text
q
ownership
status
industry
location
limit
offset
```

返回 canonical Job、Company 和来源列表。

### `GET /api/jobs/stats`

当前统计：

```text
total
with_url_unverified
without_url
central_soe
local_soe
unknown
```

---

## 9. 真实上游快照验证结果

使用 2026-09-16 用户提供的本地快照执行：

```powershell
python .\scripts\import_job_sources.py `
  --workfind-db .\third_party\upstreams\_local\workfind\国企数据库.db `
  --workfind-relations .\third_party\upstreams\_local\workfind\央企二级子公司.json `
  --xiaozhao-jobs .\third_party\upstreams\_local\xiaozhao-radar\jobs.json `
  --data-dir .\local-data\job-radar
```

WorkFind：

```text
records_seen:       2274
companies_created:  2271
sources_created:    2271
relations_created:   111
```

Xiaozhao：

```text
source rows:         1598
canonical jobs:      1486
```

当前 canonical Job 状态：

```text
DISCOVERED_URL_UNVERIFIED: 1125
DISCOVERED_NO_URL:          361
```

注意：源数据审计中有 362 个 Xiaozhao 原始行 `u` 为空；去重发生后 canonical Job 的无 URL 数量为 361，因此不能把 source-row 数和 canonical-job 数直接比较。

当前 Job 企业性质解析结果：

```text
central_soe jobs: 13
local_soe jobs:   13
unknown jobs:   1460
```

这里 `unknown` 很高并不是系统宣称这些企业“不是国企”，而是当前 Resolver 只使用可证明的名称/别名关系。下一阶段可以继续增强 Company Resolver 和官方来源验证，但不能为了提高命中率而模糊匹配错误企业。

---

## 10. 当前边界

本阶段已经解决：

- 企业主库导入；
- 央企/地方国企/未知身份建模；
- 部分央企子公司关系；
- Xiaozhao Feed 导入；
- Company Resolver；
- Job Deduper；
- Provenance；
- Job API；
- 第一版岗位雷达 UI。

本阶段明确没有实现：

- 官方招聘 URL 自动验证；
- ATS 类型识别；
- 岗位是否真实开放的自动确认；
- 浏览器登录与自动申请；
- Resume / Candidate Profile 匹配；
- 自动提交。

这些能力必须建立在当前 canonical data model 之上，而不是绕过它直接操作上游 Feed。
