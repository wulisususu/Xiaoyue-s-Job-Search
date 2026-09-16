# 央国企 AI 求职工作台
## Expert Architecture & Development Plan V1

## 一、产品定位

产品不是“一键海投软件”，而是：

**央国企岗位雷达 + 个人求职知识库 + 简历版本库 + AI 网申 Agent + 投递 CRM。**

核心目标：

1. 自动持续获取央企、国企、地方国企以及其子公司的校招信息。
2. 只把真正可以申请的岗位呈现为“开始投递”。
3. 用户只维护一次个人资料，之后所有官网重复表单尽量自动填写。
4. 简历、作品集等附件统一管理，可以针对不同岗位选择不同版本。
5. AI 可以读取网页结构和视觉内容，但不能凭空生成个人事实。
6. 登录、验证码、敏感声明和最终提交保持人工参与。
7. 每一次投递都自动留档，防止重复申请，并记录具体用了哪一份简历。
8. 所有个人资料默认 local-first，不依赖云端数据库。

---

# 二、四个开源项目如何分工

## 2.1 WorkFind —— 企业主库

WorkFind 不应该直接承担整个职位搜索前端，而应该成为：

**Company Registry / Enterprise Intelligence Source**

它目前包含：

- 全国各省国企目录；
- 国企 JSON / SQLite 数据；
- 央企二级子公司数据；
- 公司招聘官网/公众号来源登记；
- 2027 届招聘日历；
- 行业、地区、岗位、已开放等筛选能力；
- 简单投递记忆。

WorkFind 已支持例如：

`地区`
`行业`
`岗位`
`排除`
`只查已开放`

这样的结构化查询。

因此平台从 WorkFind 获取的是：

```text
公司是谁
属于什么集团
央企/地方国企
所在地区
所属行业
招聘官网是什么
招聘渠道是什么
预计什么时候开放
```

而不是简单复制 WorkFind 的 UI。

---

## 2.2 Xiaozhao Radar —— 招聘事件流

Xiaozhao Radar 作为：

**Job Feed / Recruitment Event Source**

目前项目维护 856 个招聘节点，2026-09-03 的 `jobs.json` 有 1598 条有效招聘信息；数据覆盖企业招聘官网、官方公众号和综合校招来源，并且已有周期同步机制。

它负责告诉系统：

```text
最近谁开始招人了
什么行业
什么岗位
什么时候发布
链接在哪里
```

因此：

```text
WorkFind = 企业地图
Xiaozhao Radar = 招聘雷达
```

两者必须合并，而不是二选一。

---

## 2.3 Offer Harvester —— 自动申请核心

Offer Harvester 应当成为整个系统最重要的上游参考：

**Application Automation Core**

它目前已经有：

- Playwright；
- 系统 Chrome；
- 持久化登录态；
- `--probe` 页面探测；
- `--fill-only --review`；
- 通用表单适配器；
- 专门招聘站适配器；
- 附件上传；
- 最终提交人工确认；
- SQLite/CSV；
- Dashboard；
- 岗位去重；
- 表单学习；
- Profile 事实源；
- 公司招聘官网搜索能力。

所以不要重新写一套 Playwright 自动化框架。

我们的方案应该是：

```text
Fork / Adapt Offer Harvester automation layer
              ↓
重新包装成平台 Browser Agent
```

---

## 2.4 job-application-skills —— 不作为第二套 Browser Agent

这里必须明确。

`browser-form-registration` 和 Offer Harvester 的 `job-form-filler / apply_bot`：

**存在明显功能重叠。**

两者都在做：

```text
资料读取
↓
浏览器理解
↓
表单填写
↓
文件上传
↓
人工确认
```

`job-application-skills` 另外还有一个很有价值的：

`resume-writer`

它可以从资料包生成简历并管理多版本。

因此最终采用：

```text
Offer Harvester
= 唯一浏览器执行引擎

job-application-skills
= Workflow / Prompt / Resume Strategy 参考
```

不要出现：

```text
Offer Harvester Playwright
        +
browser-form-registration Playwright
```

两套东西同时控制一个 Chrome。

否则一定会出现：

- 两套浏览器 Profile；
- 两套投递台账；
- 两套用户资料；
- 两套元素识别逻辑；
- 状态不同步；
- 一个认为已经填写，另一个重新填写。

### 最终分工

| 项目 | 保留什么 |
|---|---|
| WorkFind | 企业库、企业关系、招聘来源、招聘日历 |
| Xiaozhao Radar | 实时职位 Feed |
| Offer Harvester | Browser Agent、Portal Adapter、填表、上传、投递追踪 |
| job-application-skills | 资料包思想、resume-writer、未知表单工作流设计 |

WorkFind 是 MIT；Xiaozhao Radar 是 Apache-2.0；Offer Harvester 是 MIT。

`job-application-skills` 当前我检索到的仓库页面没有明确展示许可证，所以正式复制其中实现之前需要再检查 LICENSE；在许可证确认前把它作为设计参考最稳妥。

---

# 三、总体技术架构

推荐：

```text
┌──────────────────────────────────────┐
│           Tauri Desktop App          │
│              React UI                │
│                                      │
│ 首页 / 岗位 / 公司 / 投递 / 简历 / 设置 │
└─────────────────┬────────────────────┘
                  │
             Local IPC/API
                  │
┌─────────────────▼────────────────────┐
│            Python Core               │
│              FastAPI                 │
│                                      │
│ Profile Service                      │
│ Resume Service                       │
│ Job Service                          │
│ Application Service                  │
│ AI Service                           │
│ Browser Agent                        │
└───────┬────────┬───────────┬─────────┘
        │        │           │
     SQLite   File Vault   Playwright
        │        │           │
        │        │       Dedicated Chrome
        │        │           │
        │        │       招聘官方网站
        │
┌───────▼─────────────────────────────┐
│          Data Source Layer          │
│ WorkFind                            │
│ Xiaozhao Radar                      │
│ Offer Harvester Careers Search      │
│ 企业招聘官网                         │
└─────────────────────────────────────┘
```

重点：

**不要第一版就做云 SaaS。**

第一版做：

> Windows 单机、本地优先。

因为系统要保存：

- 姓名；
- 手机号；
- 邮箱；
- 学校；
- 教育经历；
- 求职材料；
- 简历；
- API Key；
- 招聘网站登录态。

这类数据完全没有必要先上传你的服务器。

---

# 四、第一版不建议做浏览器插件

这里我会对我们前面的讨论稍微修正。

既然现在已经确定使用 Offer Harvester，**MVP 不需要 Chrome Extension。**

因为 Offer Harvester 已经走：

```text
Playwright
+
系统 Chrome
+
Persistent Profile
```

并且已经验证了这种工作方式。

Playwright 官方支持：

```text
launchPersistentContext(userDataDir)
```

Cookie 和 LocalStorage 会存入独立 User Data Directory。

因此创建：

```text
AppData/
└── SOEJobAssistant/
    └── browser/
        └── profile/
```

用户第一次：

```text
登录中国移动
扫码
验证码
```

以后仍然是原来的登录状态。

### Chrome Extension什么时候再加？

只有未来你需要：

> “我自己随便用 Chrome 浏览网页，平台自动识别我当前所在招聘页面。”

这时候插件才非常有价值。

Chrome Content Script 可以直接访问当前页面 DOM，并与本机程序通信；Chrome 也支持 Native Messaging。

所以：

```text
V1
Playwright dedicated browser

V2/V3
Optional Chrome Extension
```

这样开发难度会下降非常多。

---

# 五、个人“知识库”不能真正按普通 RAG 来设计

你说的“知识库”，从产品上可以叫知识库。

但底层绝对不要只做：

```text
PDF
↓
Embedding
↓
Vector DB
↓
LLM问答
```

招聘表单需要的是：

**Structured Candidate Profile。**

也就是：

```text
Candidate Knowledge Base
        │
        ├── Structured Profile
        ├── Resume Library
        ├── Document Library
        ├── Answer Library
        └── Application History
```

Structured Profile 才是真正的：

**SSOT —— Single Source of Truth。**

---

# 六、“在线信息”应该怎样设计

建议页面就叫：

# 我的资料

里面分：

```text
基本信息
联系方式
教育经历
实习/工作经历
项目经历
学生工作
获奖经历
技能证书
语言能力
求职偏好
家庭/关系声明
其他常用问答
```

例如：

```json
{
  "basic": {
    "name": "...",
    "gender": "...",
    "birth_date": "...",
    "degree": "...",
    "graduation_year": 2027
  },

  "contact": {
    "phone": "...",
    "email": "..."
  },

  "education": [],
  "experience": [],
  "projects": [],
  "awards": [],
  "skills": []
}
```

每一个字段不能只有 value。

应该保存：

```text
value
source
confidence
confirmed
lastUpdated
```

例如：

```json
{
  "value": "视觉传达设计",
  "source": "resume:3",
  "confidence": 0.99,
  "confirmed": true
}
```

这样以后 AI 才不会自己猜。

---

# 七、第一次上传简历的流程

你的设想是正确的。

首次启动：

```text
欢迎
↓
配置 AI
↓
上传简历
↓
解析简历
↓
AI结构化提取
↓
生成“在线信息”
↓
用户审核
↓
完成初始化
```

处理 PDF 时：

```text
PDF
 ↓
文本解析
 ↓
有文字？
 ├─ YES → Parser
 └─ NO  → OCR
          ↓
      Structured Extraction
          ↓
     Candidate Profile
```

应该遵循：

> Parser 优先，OCR 兜底。

因为正常 PDF 简历里面本身就有文字层。

---

# 八、简历库

简历不能覆盖。

必须版本化。

例如：

```text
简历库

通用母版
├─ V1
├─ V2
└─ V3

央国企
├─ 综合管理版
├─ 视觉设计版
└─ 宣传文化版

针对岗位
├─ 中国移动-视觉设计
├─ 中国电信-企业文化
└─ 中国建筑-宣传岗
```

数据库：

```text
resumes

id
name
category
target_industry
target_role
parent_resume_id
version
file_path
file_hash
parsed_text
created_at
```

非常重要：

一旦某份简历用于申请：

```text
Application
    ↓
ResumeVersion
```

必须固定。

即使后来：

```text
视觉设计 V4
```

升级：

```text
视觉设计 V5
```

中国移动那次投递仍然记录：

```text
视觉设计 V4
SHA256: xxxx
```

以后才能真正追溯。

---

# 九、“上传到平台”的文件实际上仍然是本地文件

这是你刚才最困惑的一点。

比如用户在 UI 里：

```text
上传简历.pdf
```

并不是上传云服务器。

而是：

```text
C:\Users\xxx\Downloads\简历.pdf

        ↓

复制进入

AppData\
SOEJobAssistant\
vault\
resumes\
8c0....pdf
```

UI 上看起来：

> 已上传到简历库。

其实它仍然存在本机。

因此公司官网需要上传简历时完全没有问题。

Playwright 官方的：

```text
setInputFiles()
```

可以直接设置 `<input type=file>`，甚至支持直接上传内存 Buffer；动态出现的文件选择器也支持 `filechooser`。

因此：

```text
招聘网站
上传简历

    ↓

系统识别：
这是 Resume Upload

    ↓

Resume Vault

    ↓

视觉设计 V4.pdf

    ↓

Playwright.setInputFiles()

    ↓

上传完成
```

不需要人工拖文件。

---

# 十、未来如果做云同步也不会破坏架构

假设未来文件真的存在云端：

```text
Cloud Storage
       ↓
Encrypted File
       ↓
下载到临时缓存
       ↓
Playwright Upload
       ↓
删除 Temp
```

或者直接获取文件 Buffer：

```text
Cloud
↓
Buffer
↓
Playwright
```

所以文件上传不是技术障碍。

---

# 十一、岗位数据库设计

至少需要：

```text
companies
company_aliases
company_sources

jobs
job_sources
job_snapshots

applications
application_events

candidate_profiles

resumes
resume_versions
documents

answers

browser_sessions

form_templates
form_fields

ai_providers
```

不要把所有东西塞进一个 `jobs` 表。

---

# 十二、WorkFind + Xiaozhao Radar 如何合并

WorkFind导入：

```text
company
parent_company
ownership
province
industry
career_home
source
estimated_open_date
```

Xiaozhao导入：

```text
job_title
company_name
location
publish_date
deadline
url
category
```

随后运行：

```text
Company Resolver
```

做：

```text
“中国移动通信集团有限公司”
“中国移动”
“移动集团”

       ↓

company_id = 102
```

否则同一家企业会重复很多次。

---

# 十三、招聘链接必须分成三种 URL

这个非常关键。

不能只保存：

```text
url
```

应该分：

```text
source_url
career_home_url
apply_url
```

例如：

```text
source_url
公众号招聘公告

career_home_url
中国移动招聘首页

apply_url
中国移动-视觉设计岗-申请页面
```

你的：

**开始投递**

按钮必须只使用：

```text
apply_url
```

---

# 十四、“开放岗位”必须严格区分

岗位状态：

```text
VERIFIED_OPEN
PREDICTED_OPEN
UPCOMING
UNKNOWN
CLOSED
```

例如 WorkFind 根据历史预测：

```text
预计 9 月开放
```

只能显示：

> 预计开放

绝对不能显示：

> 立即申请。

只有：

```text
VERIFIED_OPEN
+
Official Apply URL
```

才显示：

# 开始投递

---

# 十五、招聘链接验证器

增加：

```text
Job URL Verifier
```

当 Xiaozhao Radar / WorkFind 返回链接：

```text
发现岗位
↓
检查 URL
↓
跟踪 redirect
↓
检查 domain
↓
识别职位详情
↓
判断是否存在 Apply
↓
生成 canonical_apply_url
```

最终展示：

```text
✓ 官方招聘网站
✓ 岗位仍开放
✓ 找到申请入口

[开始投递]
```

这会解决你特别强调的：

> 不能跳去一个企业介绍页面。

---

# 十六、完整投递流程

最终用户体验应该是：

```text
打开桌面程序
        ↓
本地解锁
        ↓
同步招聘数据
        ↓
岗位中心
        ↓
行业/地区/岗位/央企筛选
        ↓
岗位详情
        ↓
[开始投递]
        ↓
启动 Recruitment Chrome
        ↓
进入 apply_url
        ↓
是否需要登录？
     /        \
   YES        NO
   ↓           ↓
用户完成       继续
登录/验证码
     \        /
        ↓
[开始 AI 填写]
        ↓
DOM 页面解析
        ↓
字段语义识别
        ↓
Candidate Profile 映射
        ↓
生成 Fill Plan
        ↓
填写普通字段
        ↓
上传 Resume / Portfolio
        ↓
处理动态字段
        ↓
视觉模型兜底
        ↓
人工审核
        ↓
用户点击最终提交
        ↓
Success Detector
        ↓
自动记录 Application
```

---

# 十七、OCR 不应该成为主要技术路线

这个是整个项目是否稳定的关键。

不要：

```text
Screenshot
↓
OCR
↓
让AI猜哪里是输入框
↓
鼠标坐标点击
```

优先：

```text
DOM
ARIA
LABEL
placeholder
name
id
options
附近文字
```

形成：

```json
{
  "type": "select",
  "label": "最高学历",
  "options": [
    "本科",
    "硕士",
    "博士"
  ]
}
```

然后 AI 只需要判断：

```text
candidate.education.degree

        ↓

本科
```

---

# 十八、视觉模型在哪里用

模型仍然必须支持 Vision。

但视觉只做 fallback。

三级识别：

```text
Level 1
DOM Semantic Extraction

        ↓失败

Level 2
DOM + Screenshot Crop + Vision

        ↓失败

Level 3
Human Assistance
```

视觉主要解决：

```text
自定义组件
Canvas
没有语义的图标按钮
奇怪的下拉框
动态上传区域
图片式表单
页面提示
```

而不是每个输入框都 OCR。

---

# 十九、页面元素标准化模型

Browser Analyzer 应输出统一 Field Schema：

```json
{
  "fieldId": "F17",
  "type": "text",
  "label": "毕业院校",
  "required": true,
  "placeholder": "",
  "options": [],
  "locator": "...",
  "confidence": 0.98
}
```

再交给 AI：

```text
Field F17
毕业院校

↓

profile.education[0].school
```

结果：

```json
{
  "fieldId": "F17",
  "source": "profile.education[0].school",
  "value": "...",
  "confidence": 0.99,
  "action": "fill"
}
```

---

# 二十、AI 必须先生成 Fill Plan

严禁模型边看边乱点。

流程应该：

```text
Analyze
↓
Plan
↓
Validate
↓
Execute
```

例如：

```text
准备填写 42 个字段

自动填写       34
自动选择        5
上传文件        1
需要人工确认    2

[开始执行]
```

这样可审计。

---

# 二十一、高风险字段单独分类

建议字段安全等级：

### GREEN

例如：

```text
姓名
手机号
邮箱
学校
专业
学历
经历
技能
```

已确认后可自动填写。

### YELLOW

例如：

```text
是否接受调剂
期望城市
期望薪资
岗位偏好
是否接受派驻
```

可存默认偏好，但建议标记。

### RED

例如：

```text
是否受过刑事处罚
是否受到处分
是否存在利益冲突
是否有亲属在集团任职
真实性声明
回避关系
```

必须来源于：

**用户已经明确确认过的事实。**

没有答案：

```text
STOP
```

而不是让 AI 猜。

---

# 二十二、浏览器 Agent 内部架构

采用：

```text
BrowserSessionManager

PortalDetector

PageAnalyzer

FieldExtractor

FieldMapper

ActionPlanner

ActionExecutor

UploadManager

VisionFallback

SuccessDetector
```

其中：

### PortalDetector

识别：

```text
Moka
北森
飞书招聘
Hotjob
智联
腾讯
自研 ATS
Generic
```

### Portal Adapter接口

统一：

```text
probe()
extract()
fill()
upload()
validate()
```

`submit()` 单独管理。

Offer Harvester 已经明确区分搜索、探测、填写、上传、提交能力，这一点应该直接继承。

---

# 二十三、不要让 Adapter 自己保存用户信息

错误架构：

```text
MokaAdapter
自己一份 Profile

FeishuAdapter
自己一份 Profile
```

正确：

```text
Candidate Profile
         ↓
Field Mapping Layer
         ↓
Portal Adapter
```

Portal只关心：

> 怎么操作网页。

而不是：

> 用户是谁。

---

# 二十四、投递状态机

不能只有：

```text
未投
已投
```

建议：

```text
DISCOVERED
SAVED
OPENED

APPLICATION_STARTED

LOGIN_REQUIRED

PARTIALLY_FILLED

REVIEW_REQUIRED

SUBMITTED

ACKNOWLEDGED

WRITTEN_TEST

INTERVIEW

OFFER

REJECTED

WITHDRAWN

CLOSED
```

---

# 二十五、Application Event Log

每次变化都写事件：

```text
application_events
```

例如：

```text
2026-09-16 14:01
OPENED

2026-09-16 14:05
LOGIN_COMPLETED

2026-09-16 14:06
AI_FILL_STARTED

2026-09-16 14:07
REVIEW_REQUIRED

2026-09-16 14:10
SUBMITTED
```

这样以后才能看到完整历史。

---

# 二十六、防重复投递

判重优先级：

```text
1 ATS job ID

2 canonical apply URL

3 company + job title + location + batch

4 semantic fingerprint
```

例如：

```text
China Mobile
视觉设计
南京
2027 Campus
```

计算 fingerprint。

进入岗位时：

```text
⚠ 你已经申请过该岗位

申请时间
2026-09-09 14:23

使用简历
视觉设计 V4

状态
等待笔试

[查看记录]

[仍然进入官网]
```

但不要完全禁止用户访问。

---

# 二十七、提交成功如何记录

两种方式同时保留。

### 自动检测

SuccessDetector检查：

```text
URL改变
感谢申请
投递成功
申请已提交
Application submitted
进度中心新增记录
```

AI判断：

```text
submission_probability = 0.98
```

则系统：

```text
建议标记：已提交
```

### 人工按钮

始终保留：

```text
[标记已投递]
```

避免网页特殊导致识别失败。

---

# 二十八、AI 配置中心

第一次启动需要：

# AI Providers

支持 OpenAI-Compatible：

```text
Provider Name

Base URL

API Key

Model

Vision Model

Temperature

Timeout
```

建议架构支持两个模型：

```text
Reasoning Model
Vision Model
```

它们可以是同一个，也可以不同。

模型能力：

```text
text
vision
structured_output
```

应用启动时运行 capability test。

---

# 二十九、API Key安全

API Key：

不要：

```text
SQLite 明文
```

应该：

```text
Windows Credential Manager
```

或系统 Secret Store。

数据库只保存：

```text
secret_ref
```

而不是 Key。

---

# 三十、视觉隐私保护

非常重要。

网页截图可能已经包含：

```text
姓名
手机号
邮箱
身份证部分信息
```

因此送视觉 API 前：

```text
优先截取局部区域
```

而不是整屏。

最好：

```text
Screenshot
↓
Blur known PII
↓
Crop
↓
Vision API
```

可以提供：

```text
隐私模式
```

不开启外部 Vision 时：

```text
DOM + Local OCR
```

---

# 三十一、推荐数据库实体关系

核心结构：

```text
User
 │
 ├── CandidateProfile
 │
 ├── Resume
 │      └── ResumeVersion
 │
 ├── Document
 │
 └── Application
         │
         ├── ApplicationEvent
         └── ResumeVersion

Company
 │
 ├── CompanySource
 │
 └── Job
       │
       ├── JobSource
       ├── JobSnapshot
       └── Application
```

---

# 三十二、本地登录怎么做

第一版其实不需要互联网帐号。

你看到的：

```text
登录
```

实际应该是：

# 解锁我的求职空间

使用：

```text
本地密码
```

或者：

```text
Windows Hello
```

这样就可以保护：

```text
简历
API Key
个人信息
求职历史
```

未来真正需要：

```text
跨电脑同步
手机查看
云备份
```

时，再加云账号。

不要第一版就承担：

```text
服务端认证
对象存储
多租户
权限系统
同步冲突
```

---

# 三十三、软件目录建议

```text
soe-job-agent/

apps/
  desktop/
  frontend/

services/
  core-api/
  browser-agent/

packages/
  domain/
  schemas/
  ai/
  job-normalizer/

integrations/
  workfind/
  xiaozhao/
  offer-harvester/

portals/
  generic/
  moka/
  beisen/
  feishu/
  hotjob/

data/
  migrations/

tests/
  fixtures/
  mock-portals/
```

不要直接把四个仓库代码混在根目录。

一定要建 Integration Layer。

---

# 三十四、开源项目同步策略

每个上游保留：

```text
upstream name
upstream commit
imported version
local patches
```

例如：

```text
integrations/
offer-harvester/
UPSTREAM.md
```

记录：

```text
Repo
Commit
License
Imported modules
Local modifications
```

这样上游更新时才不会无法合并。

---

# 三十五、信息采集管线

设计：

```text
Startup
↓
Source Sync
↓
WorkFind Import
↓
Xiaozhao Import
↓
Offer Harvester Company Careers Search
↓
Normalize
↓
Resolve Company
↓
Deduplicate Job
↓
Verify URL
↓
Store Snapshot
↓
Update UI
```

这里 Offer Harvester 自己现在也已经包含 `company-careers-search`，支持包括 Moka、飞书招聘等多种公司招聘系统搜索，因此可以作为 WorkFind/Xiaozhao 的“官网复核器和补充来源”，而不是第三份平级岗位主库。

---

# 三十六、数据源权重

建议：

```text
企业官方具体 Job API/Page
100

企业官方招聘首页
95

企业官方公众号
90

国资委/地方国资委
90

WorkFind verified source
85

Xiaozhao Radar
80

其他聚合网站
60
```

但：

**来源权重和岗位匹配度必须分开。**

---

# 三十七、岗位筛选 UI

左侧：

```text
企业性质
央企
地方国企

行业

地区

岗位类别

学历要求

招聘状态

发布时间

截止时间

已申请
未申请

已收藏
```

顶部：

```text
只看可立即申请
```

这个非常重要。

---

# 三十八、岗位 Card

例如：

```text
中国XX集团

视觉设计岗

央企 · 上海

2027校园招聘

✓ 官方申请地址已验证

截止：
10月15日

来源：
Xiaozhao Radar
Official Careers

匹配：
较高

[查看详情]

[开始申请]
```

---

# 三十九、简历自动推荐

后期可以：

```text
Job JD
↓
Skills/Keyword Extractor
↓
Resume Library
↓
Match
```

显示：

```text
视觉设计 V4     92%
宣传文化 V3     86%
综合版 V6       72%
```

但不要在 MVP 第一阶段做自动生成。

第一阶段：

**先让用户自己选择简历。**

等整个投递链路稳定以后，再增加：

```text
AI定制简历
```

---

# 四十、开发优先级

## Phase 0 —— 上游审计

完成：

```text
WorkFind
Xiaozhao
Offer Harvester
job-application-skills
```

四仓：

- License；
- 数据结构；
- 接口；
- 更新方式；
- 可复用模块；
- 冲突模块。

产物：

```text
UPSTREAM_MATRIX.md
```

---

## Phase 1 —— 平台骨架

完成：

```text
Tauri
React
FastAPI
SQLite
File Vault
Settings
Local Unlock
```

验收：

启动程序能够进入：

```text
首页
我的资料
简历库
岗位
投递
设置
```

---

## Phase 2 —— 用户资料与简历库

完成：

```text
PDF上传
DOCX上传
简历文本解析
AI结构化
Profile生成
人工校验
ResumeVersion
附件Vault
```

验收：

上传一份 PDF 后能够自动生成在线信息。

---

## Phase 3 —— 招聘雷达

完成：

```text
WorkFind Importer
Xiaozhao Importer
Company Resolver
Job Normalizer
Job Deduper
```

验收：

一个岗位多个来源只能显示一次。

---

## Phase 4 —— Apply URL Verification

完成：

```text
官方域名检查
Redirect解析
岗位状态检测
Apply入口识别
```

验收：

只有真正能够进入招聘申请链路的职位显示：

```text
开始申请
```

---

## Phase 5 —— Browser Agent MVP

直接基于 Offer Harvester。

完成：

```text
Dedicated Chrome
Persistent Profile
Probe
Form Analyze
Generic Fill
Review
```

验收：

能够打开一个测试招聘页面并自动填：

```text
姓名
电话
邮箱
学校
专业
```

---

## Phase 6 —— File Upload

完成：

```text
Resume Semantic Detection
File Input Detection
Resume Vault Selection
Playwright Upload
```

验收：

平台简历库里的 PDF 能直接上传到招聘网站。

---

## Phase 7 —— Vision Fallback

完成：

```text
Screenshot Crop
Multimodal API
Element Resolution
```

验收：

DOM 无法判断的控件可以请求 Vision 辅助。

---

## Phase 8 —— Application CRM

完成：

```text
状态机
事件记录
Resume Snapshot
防重复
成功识别
人工标记
```

验收：

投递完成以后：

```text
公司
岗位
URL
日期
简历
状态
```

完整可查。

---

## Phase 9 —— ATS专项适配

根据实际使用频率开发，而不是一开始全写。

优先：

```text
Generic
Moka
北森
飞书招聘
Hotjob
```

以后看到某个央企频繁使用某系统：

```text
再增加 Adapter
```

---

## Phase 10 —— 简历 AI

最后再接：

```text
resume-writer
```

形成：

```text
JD
↓
当前 Profile
↓
Master Resume
↓
生成 Tailored Resume
↓
人工审阅
↓
进入 Resume Vault
↓
申请
```

而不是 AI 每投一个岗位自动偷偷改简历。

---

# 四十一、测试策略

这类项目真正难的是招聘网站一直变。

因此必须建立：

```text
tests/mock-portals/
```

模拟：

```text
普通HTML
React表单
Moka风格
北森风格
动态下拉
多教育经历
文件上传
Shadow DOM
iframe
```

每次修改 Browser Agent 都跑。

同时真实招聘网站：

```text
仅 probe
```

做低频 smoke test。

Offer Harvester 自己也采用无浏览器核心回归 + 必要时真实站点冒烟测试的模式，这一点值得沿用。

---

# 四十二、最重要的架构原则

整个项目必须遵循：

```text
Data Source ≠ Truth

Resume ≠ Profile

AI ≠ Truth

Browser Agent ≠ Decision Maker
```

真正的数据关系是：

```text
简历
   ↓
提取候选事实
   ↓
用户确认
   ↓
Candidate Profile
   ↓
唯一事实源
   ↓
AI映射
   ↓
网页字段
```

而不是：

```text
网页问什么
↓
AI现场编什么
```

---

# 四十三、最终产品形态

最终软件打开后应该只有几个一级入口：

```text
首页

岗位雷达

投递中心

我的资料

简历库

设置
```

首页：

```text
今日新增岗位
可申请岗位
已收藏
填写中
已投递
笔试
面试
Offer
```

这比把 WorkFind、Xiaozhao 和 Offer Harvester 四个项目的 UI 直接拼起来要成熟得多。

---

# 四十四、最终技术选型

第一版推荐确定为：

```text
Desktop
Tauri 2

Frontend
React + TypeScript

Backend/Core
Python 3.11+
FastAPI

DB
SQLite
后期可考虑 SQLCipher

ORM
SQLModel / SQLAlchemy

Browser
Google Chrome / Microsoft Edge

Automation
Playwright

Automation Base
Offer Harvester

Company Registry
WorkFind

Recruitment Feed
Xiaozhao Radar

Resume Workflow Reference
job-application-skills

AI
OpenAI-Compatible Provider Adapter

Vision
Multimodal LLM

Secrets
OS Credential Store

File Storage
Local File Vault
```

Tauri 2 本身支持 sidecar 模式，因此 Python Core 可以作为随桌面程序启动的本机子进程。

---

# 四十五、我认为最合理的 MVP 边界

第一版千万不要追求：

```text
100%自动
全央企
所有ATS
自动提交
云同步
手机APP
AI自动改简历
```

第一版做到下面这些，就已经有非常强的实际价值：

```text
✓ 上传简历

✓ 自动建立在线资料

✓ WorkFind企业库

✓ Xiaozhao岗位库

✓ 筛选当前开放职位

✓ 跳转真实申请地址

✓ 使用独立Chrome登录

✓ AI自动填普通字段

✓ 自动选择并上传简历

✓ 人工处理特殊字段

✓ 人工最终提交

✓ 自动保存投递记录

✓ 防重复申请
```

如果能把一个原来：

**10～15 分钟**

的普通央国企网申，稳定压缩到：

**3～5 分钟**

这个项目第一阶段就已经成功。

更重要的是，它不是通过“暴力全自动点击”实现，而是把真正重复的工作消掉，同时保留需要本人判断的节点。

---

# 四十六、架构最终结论

四个项目不要简单拼接运行。

正确关系是：

```text
             WorkFind
                │
            企业知识
                │
                ▼
Xiaozhao ─── Job Core ─── Official Careers
 Radar          │
                │
                ▼
          Platform Database
                │
       ┌────────┴────────┐
       │                 │
Candidate Profile    Resume Vault
       │                 │
       └────────┬────────┘
                │
                ▼
           AI Planner
                │
                ▼
        Offer Harvester
        Browser Engine
                │
                ▼
       Recruitment Website
                │
                ▼
       Human Review / Submit
                │
                ▼
          Application CRM
```

而：

```text
job-application-skills
```

位于旁边作为：

```text
Resume Workflow
Form Workflow
Design Reference
```

不要成为另一套平行运行时。

这就是我建议锁定的 V1 总体架构。