# 小悦求职 UI 现代化升级方案（参考 Motrix Turbo）

> 日期：2026-09-18  
> 基线：`main@ef803c98f8b7719b1719fcb245e872d0e5c4b2dd`  
> 状态：Implementation Plan  
> 适用范围：Windows 桌面端 UI、桌面交互层、安装目录整理  
> 非目标：不把 Tauri 改成 Electron，不重写现有 FastAPI / SQLAlchemy / SQLite / Browser Agent / Profile SSOT / Resume Vault 业务链路

---

## 1. 目标

本次升级的核心不是“把小悦改成 Motrix”，而是借鉴 Motrix Turbo 当前已经验证过的桌面 UI 工程组织方式，补齐小悦现有 UI 工程层。

目标架构：

```text
Tauri 2
└── React Renderer
    │
    ├── Design System
    │   ├── Tailwind CSS 4
    │   ├── shadcn/ui
    │   ├── Base UI
    │   ├── Lucide
    │   └── Design Tokens
    │
    ├── Desktop Kit
    │   ├── AppSidebar
    │   ├── WindowChrome
    │   ├── PanelShell
    │   ├── PageHeader
    │   ├── CommandPalette
    │   ├── EmptyState
    │   └── VirtualList
    │
    ├── Feature Layer
    │   ├── Dashboard
    │   ├── Jobs
    │   ├── Applications
    │   ├── Profile
    │   ├── Resumes
    │   └── Settings
    │
    └── API Client
        ↓
FastAPI Sidecar
        ↓
SQLAlchemy / SQLite / AI / Browser Agent
```

最终原则：

> **UI 学 Motrix，桌面底座继续 Tauri，AI/自动化继续 Python。**

---

## 2. 当前现状

当前桌面端已经具备：

- Tauri 2；
- React 19；
- TypeScript；
- Vite；
- React Router；
- Vitest / Testing Library；
- Rust shell；
- FastAPI sidecar；
- SQLAlchemy + Alembic + SQLite；
- PyInstaller onedir；
- NSIS；
- WebView2；
- session token / loopback API / sidecar 健康检查。

当前 UI 的主要问题不在“能不能跑”，而在工程组织和视觉层：

1. `apps/desktop/src/styles/global.css` 中存在大量页面级手写 CSS；
2. `.primary-button`、`.secondary-button`、`.soft-badge`、`.job-card`、`.sidebar` 等组件样式分散在全局 CSS；
3. 页面组件直接承担较多布局、业务状态和视觉逻辑；
4. `JobsPage.tsx` 已经开始趋向“大页面组件”；
5. 缺少统一 Design Token；
6. 缺少组件 primitive 层；
7. 缺少 desktop-kit 层；
8. 暂无统一 Dark Mode；
9. Sidebar、标题栏、弹窗、Toast、Empty State 等桌面交互还没有形成统一系统；
10. 大量岗位时仍以大卡片列表展示，不适合 PC 桌面高密度信息。

---

## 3. Motrix 中要借鉴的部分

Motrix 当前前端工程已经形成清晰三层：

```text
components/ui/
    ↓
components/desktop-kit/
    ↓
feature / route composition
```

对应小悦：

```text
ui/
    最小化视觉 primitive

desktop-kit/
    桌面交互、Sidebar、Panel、Window Chrome、Virtual List

features/
    岗位、投递、资料、简历、设置等业务页面
```

只借鉴以下工程思想：

- shadcn primitive；
- Base UI；
- Tailwind Design Token；
- CVA variant；
- Lucide；
- Sidebar inset；
- Page / Panel shell；
- desktop-kit；
- settings-kit；
- Virtual List；
- Toast / Dialog / Tooltip；
- reduced motion；
- Light / Dark theme；
- E2E / Screenshot Regression。

**禁止直接复制 Motrix 品牌、Logo、文案、插画和专有视觉资产。**

---

## 4. 本次明确不做

以下事项不属于 UI 升级：

- 不迁移到 Electron；
- 不删除 Tauri；
- 不删除 Rust；
- 不把 FastAPI 重写成 Node.js；
- 不把 Python sidecar 改成 Electron main process；
- 不更换 SQLite / SQLAlchemy / Alembic；
- 不修改 Profile SSOT 的业务原则；
- 不绕过 Draft Review；
- 不重写 Job Canonical Model；
- 不改变 Browser Agent 的 Human Confirm Gate；
- 不因为 UI 重构而修改业务 API 语义；
- 不为了“看起来像正常桌面软件”人为增加 DLL。

---

# 5. 前端依赖升级方案

## 5.1 第一阶段新增

优先加入：

```text
tailwindcss
@tailwindcss/vite

shadcn
@base-ui/react

lucide-react
class-variance-authority
clsx
tailwind-merge
tw-animate-css

react-hook-form
zod
@hookform/resolvers

cmdk
@tanstack/react-virtual
```

可选：

```text
recharts
next-themes
```

## 5.2 暂时不要一起升级

当前先不要为了追 Motrix 版本同步升级：

- Vite；
- TypeScript；
- Vitest；
- React Router 大版本。

原则：

> **先完成 UI 架构迁移，再单独升级工具链。**

避免 UI 重构与构建工具迁移同时发生，降低回归定位难度。

---

# 6. 目录结构重构

目标目录：

```text
apps/desktop/src/
├── app/
│   ├── App.tsx
│   └── routes.tsx
│
├── components/
│   ├── ui/
│   │   ├── button.tsx
│   │   ├── badge.tsx
│   │   ├── card.tsx
│   │   ├── input.tsx
│   │   ├── select.tsx
│   │   ├── dialog.tsx
│   │   ├── alert-dialog.tsx
│   │   ├── dropdown-menu.tsx
│   │   ├── tooltip.tsx
│   │   ├── sheet.tsx
│   │   ├── tabs.tsx
│   │   ├── skeleton.tsx
│   │   ├── separator.tsx
│   │   ├── switch.tsx
│   │   ├── progress.tsx
│   │   └── toast.tsx
│   │
│   ├── desktop-kit/
│   │   ├── app-sidebar.tsx
│   │   ├── window-chrome.tsx
│   │   ├── page-header.tsx
│   │   ├── panel-shell.tsx
│   │   ├── command-palette.tsx
│   │   ├── empty-state.tsx
│   │   ├── status-indicator.tsx
│   │   ├── data-table.tsx
│   │   ├── inspector-panel.tsx
│   │   └── virtual-list.tsx
│   │
│   └── settings-kit/
│       ├── settings-section.tsx
│       ├── settings-row.tsx
│       └── provider-card.tsx
│
├── features/
│   ├── dashboard/
│   ├── jobs/
│   ├── applications/
│   ├── profile/
│   ├── resumes/
│   └── settings/
│
├── api/
├── lib/
├── hooks/
│
└── styles/
    ├── globals.css
    └── tokens.css
```

规则：

1. `components/ui/` 不允许放业务逻辑；
2. `desktop-kit/` 只放通用桌面行为；
3. feature-specific 组件放 `features/<feature>/`；
4. API client 保持现有单一职责；
5. 页面不允许重新复制一份 Button / Dialog / Badge；
6. 新页面不得继续扩张全局页面 CSS；
7. 业务状态不得通过视觉组件私自持久化。

---

# 7. Design Token

当前散落的：

```text
#172033
#718096
#e1e7f0
...
```

需要逐步收敛为 token。

建议：

```css
--background
--foreground

--card
--card-foreground

--popover
--popover-foreground

--primary
--primary-foreground

--secondary
--secondary-foreground

--muted
--muted-foreground

--accent
--accent-foreground

--success
--success-foreground

--warning
--warning-foreground

--destructive
--destructive-foreground

--border
--input
--ring

--sidebar
--sidebar-foreground
--sidebar-accent
--sidebar-accent-foreground
--sidebar-border
--sidebar-inset
```

页面应使用：

```text
bg-background
bg-card
text-foreground
text-muted-foreground
border-border
bg-primary
```

而不是直接写十六进制颜色。

---

# 8. UI Primitive 规范

## 8.1 Button

统一 API：

```tsx
<Button>开始申请</Button>
<Button variant="outline">验证入口</Button>
<Button variant="ghost">取消</Button>
<Button variant="destructive">删除</Button>
```

Variant：

```text
default
secondary
outline
ghost
destructive
link
```

Size：

```text
xs
sm
default
lg
icon
```

逐步删除：

```text
.primary-button
.secondary-button
```

## 8.2 Badge

至少支持：

```text
default
secondary
success
warning
destructive
outline
```

用于：

- 央企；
- 地方国企；
- 已验证；
- 待验证；
- 待重发现；
- ATS；
- Draft 状态；
- Application 状态。

逐步删除：

```text
.soft-badge
.soft-badge.warning
.soft-badge.verified
```

## 8.3 必须统一的 primitive

- Button；
- Badge；
- Card；
- Input；
- Select；
- Dialog；
- Alert Dialog；
- Tooltip；
- Dropdown Menu；
- Tabs；
- Sheet / Drawer；
- Skeleton；
- Separator；
- Switch；
- Progress；
- Toast。

---

# 9. Desktop Shell

## 9.1 目标布局

当前普通后台式布局升级成 inset desktop layout：

```text
╭──────────────────────────────────────────────────╮
│ 小悦求职                           🔍   ─ □ ×     │
│                                                  │
│ ┌──────────┐  ╭──────────────────────────────╮  │
│ │   悦     │  │                              │  │
│ │          │  │    当前功能页面              │  │
│ │ 首页     │  │                              │  │
│ │ 岗位雷达 │  │                              │  │
│ │ 投递中心 │  │                              │  │
│ │ 我的资料 │  │                              │  │
│ │ 简历库   │  │                              │  │
│ │          │  │                              │  │
│ │ 设置     │  ╰──────────────────────────────╯  │
│ └──────────┘                                    │
╰──────────────────────────────────────────────────╯
```

内容区：

- 外边距约 8px；
- 圆角；
- 轻阴影；
- 与 Sidebar 背景分层；
- 页面自身不再承担整个窗口背景。

## 9.2 Sidebar

使用 Lucide：

```text
LayoutDashboard  首页
Radar            岗位雷达
Send             投递中心
UserRound        我的资料
Files            简历库
Settings         设置
```

Sidebar 要支持：

- 展开；
- 折叠；
- active；
- hover；
- tooltip；
- keyboard focus。

建议：

```text
展开：约 216px
折叠：约 56px
```

折叠后只保留 icon。

设置项固定在底部。

## 9.3 AppShell 拆分

现有 `AppShell.tsx` 应拆成：

```text
AppShell
├── WindowChrome
├── AppSidebar
├── SidebarInset / MainPanel
├── CoreFailureBanner
└── Outlet
```

Core 启动失败横幅必须保留，不得因 UI 重构丢失诊断能力。

---

# 10. 自定义窗口标题栏

在 Design System 与 Sidebar 稳定后再实施。

目标：

```text
┌────────────────────────────────────────────────┐
│ 悦 小悦求职             ⌕ 搜索岗位   _  □  × │
├────────────────────────────────────────────────┤
```

要求：

- 使用 Tauri Window API；
- 拖动区域使用 `data-tauri-drag-region`；
- 正确处理最小化；
- 正确处理最大化/还原；
- 正确处理关闭；
- 按钮区域不能成为 drag region；
- Windows 缩放 100% / 125% / 150% 测试；
- 最大化后边缘布局正确。

此阶段不得替换 Tauri。

---

# 11. Dashboard 升级

当前 8 个同权 metric card 信息层级过弱。

建议首页改为：

```text
╭ 今日求职状态 ─────────────────────────────────────╮

  今日新增       可申请       已投递       面试
    36            182           7            2

╰──────────────────────────────────────────────────╯

╭ 求职进度 ─────────────────╮ ╭ 今日建议 ───────────╮
│  已收藏 12                │ │ 3 个岗位即将截止    │
│      ↓                    │ │ 2 份申请待继续      │
│  已申请 7                 │ │ 简历资料完整度 92%  │
│      ↓                    │ │                     │
│  笔试 3                   │ ╰─────────────────────╯
│      ↓                    │
│  面试 2                   │ ╭ 数据源 ─────────────╮
│      ↓                    │ │ ● 腾讯文档 正常     │
│  Offer 1                  │ │ ● WorkFind 正常     │
╰───────────────────────────╯ ╰─────────────────────╯
```

Dashboard 目标从“数据库 KPI 墙”改成：

> **今天用户应该做什么。**

注意：必须继续按 `doc/TODO.md` 要求接真实数据，不允许用硬编码 KPI 代替。

---

# 12. 岗位雷达升级

## 12.1 主视图从大卡片改成高密度桌面列表

目标：

```text
┌──────────────────────────────────────────────────────┐
│ 岗位雷达                           同步     筛选 ⚙   │
│                                                      │
│ 🔍 搜索公司、岗位                                    │
├──────────────────────────────────────────────────────┤
│ 182 个可申请 · 26 个待验证 · 更新时间 09:41          │
├──────────────────────────────────────────────────────┤
│ 公司             岗位       地点     状态      截止  │
│──────────────────────────────────────────────────────│
│ 中国移动         视觉设计    上海     ● 可申请   9/25 │
│ 国家电网         平面设计    南京     ● 可申请   9/27 │
│ 中国电信         品牌视觉    合肥     ○ 待验证   9/30 │
│ 中粮集团         视觉设计    北京     ○ 待验证    --  │
└──────────────────────────────────────────────────────┘
```

要求：

- 适配 1000+ / 10000+ 岗位；
- 使用 `@tanstack/react-virtual`；
- 保留 server-side pagination；
- 不一次渲染全部 DOM；
- 筛选条件继续走现有 API；
- 不破坏 job canonical / provenance。

## 12.2 Inspector

点击岗位后打开右侧 Inspector：

```text
┌────────────────────────┐
│ 中国移动               │
│ 视觉设计岗             │
│                        │
│ 央企                   │
│ 上海                   │
│ 秋招 2027              │
│ Moka                   │
│                        │
│ 最近验证 09:41        │
│                        │
│ [查看官网]             │
│ [验证入口]             │
│ [开始申请]             │
└────────────────────────┘
```

只有 `VERIFIED_OPEN` 才能启用“开始申请”。

不得弱化现有验证状态门禁。

---

# 13. 数据源状态

目前数据源状态长期占据岗位页较大区域。

改为：

```text
数据源 ●
```

点击 Popover / Sheet：

```text
╭ 数据源状态 ─────────────────╮
│ ● 腾讯文档                  │
│   09:26 同步成功            │
│                             │
│ ● WorkFind                  │
│   昨日 18:21 同步成功       │
│                             │
│ [全部同步]                  │
╰─────────────────────────────╯
```

原则：

- 正常状态安静；
- 异常状态突出；
- 同步失败使用 Badge + Toast；
- Last Known Good Snapshot 语义不变；
- 不因 UI 简化而隐藏真实错误。

---

# 14. 投递中心

主视图建议：

```text
全部  已收藏  申请中  已投递  笔试  面试  Offer
```

默认使用高密度列表：

```text
中国移动   视觉设计岗   已投递    09-18
国家电网   平面设计     面试      09-20
中粮集团   UI设计       填写中    今天
```

后续可以提供：

```text
表格视图
看板视图
```

Browser Agent 运行时应复用同一 Application SSOT，并呈现步骤：

```text
● 已打开 ATS
● 基本资料已映射
● 简历已上传
◉ 正在检查表单
○ 等待人工确认
○ 提交
```

任何最终提交仍必须保留 Human Confirm Gate。

---

# 15. Profile

目标不是普通长表单，而是“可信资料工作台”。

顶部：

```text
资料完整度  ███████████████░  92%
```

分区：

```text
基本信息
教育经历
实习经历
校园经历
项目经历
获奖情况
证书
语言
技能
求职偏好
```

Draft Review：

```text
AI 从简历发现：

姓名：赵新悦
来源：简历 v7

[确认写入] [忽略]
```

必须继续遵守：

> 只有 confirmed Profile SSOT 才允许 Browser Agent 使用。

不允许上传简历后自动把 Draft 当成事实。

---

# 16. Resume Vault

目标：

- 版本列表；
- 文件名；
- 文件类型；
- SHA-256 前缀；
- 版本号；
- 解析状态；
- Draft 数量；
- OCR_REQUIRED；
- FAILED；
- 导入日期；
- 去重状态。

状态必须通过统一 Badge / Status Indicator 展示。

选中一个版本后使用 Inspector / Detail Panel 展示详情。

---

# 17. Settings

使用独立 settings-kit。

建议结构：

```text
常规
外观
AI Provider
数据源
本地数据
浏览器自动化
关于
```

统一 Settings Row：

```text
标题                     [Control]
说明文字
```

例如：

```text
主题                     [跟随系统 ▼]
选择浅色、深色或系统主题
```

Provider 表单使用：

- react-hook-form；
- zod；
- shared schema；
- Apply/Cancel；
- 提交中禁用重复提交。

---

# 18. Light / Dark / System Theme

本次 Design Token 建立后，一并支持：

```text
Light
Dark
System
```

不允许每个页面自己维护 Dark Mode CSS。

所有颜色必须通过 token 变化。

---

# 19. 动画

生产力软件，动画必须短、统一、可关闭。

建议：

```text
button hover      120ms
sidebar           180ms
panel / drawer    220ms
dialog            180ms
page fade         120ms
```

要求：

- 不做 Landing Page 大动画；
- 不让动画阻塞操作；
- 支持 `prefers-reduced-motion`；
- reduced motion 下关闭非必要 motion。

---

# 20. Command Palette

在基础 UI 稳定后增加。

推荐使用 `cmdk`。

入口：

```text
Ctrl + K
```

初期支持：

- 打开首页；
- 打开岗位雷达；
- 打开投递中心；
- 打开简历库；
- 打开设置；
- 搜索岗位；
- 手动同步数据源。

后续可增加：

- 打开指定岗位；
- 打开指定申请记录；
- 打开指定简历版本。

---

# 21. 安装目录现状说明

当前 Tauri + PyInstaller onedir 的安装结构大致为：

```text
小悦求职/
│
├── xiaoyue-job-search.exe
├── uninstall.exe
└── core-api/
    ├── xiaoyue-core-api.exe
    ├── _internal/
    ├── alembic/
    └── alembic.ini
```

这是正常结果，不是“文件太少”。

原因：

- Tauri 使用 Windows WebView2；
- 不需要像 Electron 一样附带完整 Chromium；
- Rust shell 编译进主 EXE；
- React / CSS / JS 资源被 Tauri 打包；
- Python 业务 Core 由 PyInstaller onedir 单独携带。

Electron 软件通常出现大量：

```text
*.dll
*.pak
resources.pak
locales/
app.asar
snapshot_blob.bin
v8_context_snapshot.bin
```

主要是因为 Electron 自带 Chromium / Node / V8，而不是因为它更“专业”。

---

# 22. 安装目录整理方案

建议进一步整理为：

```text
Xiaoyue Job Search/
│
├── xiaoyue-job-search.exe
├── uninstall.exe
│
└── resources/
    ├── core-api/
    │   ├── xiaoyue-core-api.exe
    │   ├── _internal/
    │   ├── alembic/
    │   └── alembic.ini
    │
    └── licenses/
```

目的：

- 根目录干净；
- 业务资源集中；
- 未来增加许可证、模型、模板等有统一位置；
- 不人为制造 DLL。

## 22.1 Tauri 配置

将当前资源目标：

```text
core-api/
```

迁移到：

```text
resources/core-api/
```

## 22.2 Rust 寻址

`find_core_bin()` 增加：

```rust
exe_dir
    .join("resources")
    .join("core-api")
    .join("xiaoyue-core-api.exe")
```

迁移期间可以临时保留旧路径兼容：

```text
core-api/xiaoyue-core-api.exe
resources/core-api/xiaoyue-core-api.exe
```

稳定一个版本后删除旧路径。

---

# 23. PyInstaller 策略

继续使用：

```text
PyInstaller onedir
```

**不要改 onefile。**

原因：

- sidecar 是常驻进程；
- onefile 会运行时解包；
- 启动更慢；
- Temp 目录增加；
- AV 误报风险通常更高；
- 故障诊断更差；
- native dependency 定位更麻烦。

当前 onedir 对 Xiaoyue Core 更合理。

---

# 24. Windows 商业化质量重点

安装目录文件数量不是质量指标。

更重要的是：

- 正确 App Icon；
- File Version；
- Product Version；
- Company Name；
- Product Name；
- NSIS 品牌化；
- Start Menu；
- 卸载项；
- 数字签名；
- 自动更新；
- 崩溃诊断；
- sidecar 日志；
- AppData 管理；
- 安装/卸载 smoke；
- sidecar 不残留；
- 数据不随卸载误删；
- 后续 Release Artifact。

不要为了“桌面软件看起来有很多文件”故意增加 DLL。

---

# 25. 实施阶段

## Phase 0 — Baseline Guard

必须先做：

- [ ] 当前 main 全测试通过；
- [ ] 记录当前 UI Screenshot；
- [ ] 记录当前 installer layout；
- [ ] 禁止 UI 重构同时修改后端数据模型；
- [ ] 禁止 UI 重构同时修改 API 语义；
- [ ] 为关键页面建立最小 smoke。

Acceptance：

- UI 改造前存在可比对基线。

---

## Phase 1 — UI Foundation

任务：

- [ ] 引入 Tailwind CSS；
- [ ] 引入 shadcn / Base UI；
- [ ] 引入 Lucide；
- [ ] 引入 CVA / clsx / tailwind-merge；
- [ ] 建立 tokens；
- [ ] Button；
- [ ] Badge；
- [ ] Card；
- [ ] Input；
- [ ] Select；
- [ ] Dialog；
- [ ] Alert Dialog；
- [ ] Tooltip；
- [ ] Dropdown；
- [ ] Tabs；
- [ ] Sheet；
- [ ] Skeleton；
- [ ] Separator；
- [ ] Switch；
- [ ] Progress；
- [ ] Toast。

约束：

- 后端零修改；
- Core client 零行为变化；
- 路由不改；
- 原功能仍可使用。

Acceptance：

- 至少一页完整使用新 primitive；
- 无重复 Button 系统；
- Build / Test 通过。

---

## Phase 2 — Desktop Shell

任务：

- [ ] AppShell 重构；
- [ ] AppSidebar；
- [ ] Sidebar inset；
- [ ] Sidebar 折叠；
- [ ] Lucide icon；
- [ ] Tooltip；
- [ ] 统一 PageHeader；
- [ ] 统一 PanelShell；
- [ ] CoreFailureBanner 保留；
- [ ] Dark Mode 基础。

Acceptance：

- 六个一级路由均可导航；
- active 状态正确；
- Sidebar 折叠不破坏布局；
- 1024px 最小窗口仍可使用；
- Core 启动失败仍可诊断。

---

## Phase 3 — 核心页面迁移

顺序固定：

```text
Dashboard
↓
Jobs
↓
Applications
↓
Profile
↓
Resumes
↓
Settings
```

每完成一个页面：

- [ ] 新组件完成；
- [ ] 对应测试通过；
- [ ] 删除该页旧 CSS；
- [ ] 禁止新旧 UI 长期并存。

Acceptance：

- `global.css` 不再承担大量业务页面样式；
- 页面主要由 primitive / desktop-kit / feature component 组合。

---

## Phase 4 — Jobs Desktop UX

任务：

- [ ] 高密度列表；
- [ ] Virtualization；
- [ ] 右侧 Inspector；
- [ ] 筛选栏；
- [ ] 搜索；
- [ ] 状态 Badge；
- [ ] 数据源 Popover；
- [ ] Sync Toast；
- [ ] Empty State；
- [ ] Loading Skeleton；
- [ ] verified gate 保持。

Acceptance：

- 1000+ job 浏览流畅；
- 10k synthetic fixture 不产生 10k 同时 DOM；
- server-side pagination 不倒退；
- 未验证岗位不能申请。

---

## Phase 5 — Desktop Interaction

任务：

- [ ] Command Palette；
- [ ] Keyboard Shortcut；
- [ ] Context Menu；
- [ ] Toast；
- [ ] Drawer / Inspector；
- [ ] Focus management；
- [ ] Reduced Motion；
- [ ] Light / Dark / System。

Acceptance：

- 键盘可完成主导航；
- Dialog/Sheet 关闭后 focus 正确恢复；
- reduced motion 生效。

---

## Phase 6 — Custom Window Chrome

任务：

- [ ] Tauri custom titlebar；
- [ ] drag region；
- [ ] minimize；
- [ ] maximize / restore；
- [ ] close；
- [ ] Windows DPI；
- [ ] 最大化 safe area。

Acceptance：

- 100% / 125% / 150% DPI 正常；
- 标题栏按钮可点击；
- drag region 不抢控件事件；
- 最大化/还原行为符合 Windows 习惯。

---

## Phase 7 — Packaging Cleanup

任务：

- [ ] `core-api/` → `resources/core-api/`；
- [ ] Rust 路径兼容；
- [ ] Installer smoke 更新；
- [ ] Uninstall smoke；
- [ ] sidecar health/auth smoke；
- [ ] 旧布局兼容清理。

Acceptance：

```text
<install>/
├── xiaoyue-job-search.exe
├── uninstall.exe
└── resources/
    └── core-api/
```

同时：

- sidecar 正常启动；
- health 200；
- auth 正常；
- 应用退出不残留 sidecar；
- 卸载成功。

---

# 26. 测试要求

## 26.1 Frontend Unit

至少覆盖：

- Sidebar active；
- Sidebar collapse；
- Button variant；
- Badge status；
- Dialog；
- Job filters；
- Job Inspector；
- Profile Draft；
- Resume state；
- Settings form；
- Core error banner。

## 26.2 E2E

新增 Playwright Desktop E2E，至少覆盖：

```text
启动
→ 首页
→ 岗位雷达
→ 筛选
→ 选择岗位
→ Inspector
→ 验证入口
→ Profile
→ Resume Vault
→ Settings
```

## 26.3 Screenshot Regression

至少固定：

```text
1280 × 820
1440 × 900
```

建议增加：

```text
1024 × 700
```

覆盖：

- Light；
- Dark；
- Sidebar expanded；
- Sidebar collapsed；
- Dialog；
- Inspector。

---

# 27. 性能要求

- Sidebar 切换不得触发整个应用不必要重渲染；
- Job 列表必须 virtualize；
- 高频状态避免全页 rerender；
- Skeleton 不应造成明显 layout shift；
- 不因为 UI 框架引入大体积无用依赖；
- 生产 build 检查 bundle；
- 首屏不得等待非必要数据；
- sidecar 启动逻辑不因 UI 重构延迟。

---

# 28. Accessibility

必须：

- keyboard navigation；
- focus-visible；
- aria-label；
- Dialog focus trap；
- Sheet focus trap；
- Tooltip 不承载唯一信息；
- Status 不只靠颜色；
- prefers-reduced-motion；
- forced-colors 基础可用；
- disabled 状态明确。

---

# 29. Agent 开发硬约束

开发智能体必须遵守：

1. 不把 Tauri 改成 Electron；
2. 不删除 Rust shell；
3. 不修改 Core API 语义来“配合 UI”；
4. 不复制 Motrix 品牌资产；
5. 不删除现有安全门禁；
6. 不允许未验证岗位启用申请；
7. 不允许 Resume Draft 自动写入 confirmed Profile；
8. 不绕过 Human Confirm；
9. 不把 API Key 写 SQLite；
10. 不把 session token 落盘；
11. 不因为 UI 迁移关闭 loopback / Origin / Host 防护；
12. 不把 PyInstaller onedir 改 onefile；
13. 不一次性重写全部页面；
14. 每个 Phase 独立提交并可回滚；
15. 每一阶段结束必须跑完整 test + build；
16. 如果 UI 改造暴露业务 bug，单独建修复提交，不和纯视觉重构混在同一提交；
17. 优先复用已有 API client，不创建第二套 client；
18. 业务 Feature 不得把领域状态复制到 primitive；
19. 新 UI 必须支持中文；
20. 保持 Windows 为当前主目标平台。

---

# 30. 多智能体并行执行计划

本项目允许主智能体启动多个子智能体并行实施，但必须采用**分波次（Wave）并行**，不能让所有 Agent 从同一个旧基线同时改共享文件。

核心原则：

> **先冻结共享契约，再并行 feature；共享文件只能有一个 Owner；主智能体只做编排、审查、合并和冲突处理。**

---

## 30.1 角色拓扑

建议由 **1 个主智能体（Orchestrator）+ 8 个执行/验证子智能体**组成。

| 角色 | 代号 | 主要职责 | 是否长期存在 |
|---|---|---|---|
| 主智能体 / 集成负责人 | ORCH | 基线、任务编排、契约冻结、合并、冲突处理、最终验收 | 是 |
| 基础 UI / Design System | UI-FOUNDATION | Tailwind、tokens、shadcn/Base UI、primitive | Wave 1 |
| Desktop Shell | UI-SHELL | AppShell、Sidebar、Inset、PageHeader、PanelShell | Wave 2 |
| Jobs 体验 | UI-JOBS | Job 高密度列表、virtualization、Inspector、筛选、数据源 UI | Wave 3 |
| Dashboard + Applications | UI-DA | 首页、投递中心 | Wave 3 |
| Profile + Resume | UI-PR | Profile SSOT UI、Draft Review、Resume Vault | Wave 3 |
| Settings | UI-SETTINGS | settings-kit、设置页、Provider / 数据源 / 外观 UI | Wave 3 |
| Desktop / Packaging | DESKTOP | Tauri Window Chrome、安装资源布局、Rust 路径、NSIS smoke | Wave 4/5 |
| QA / E2E / Visual | QA | 基线截图、E2E、视觉回归、A11y、性能回归 | 全程观察，后期集中落地 |

如果主智能体并发能力有限，优先保留：

```text
ORCH
UI-FOUNDATION
UI-SHELL
UI-JOBS
UI-PR
UI-DA
DESKTOP
QA
```

Settings 可并入 UI-DA。

---

## 30.2 Git / Worktree 执行模型

主智能体必须先创建一个总集成分支：

```text
feat/ui-modernization
```

从当前 main 的**明确 SHA**创建，不允许子智能体各自从“当时最新 main”随意开工。

每个子智能体使用独立 branch + worktree：

```text
feat/ui-modernization
│
├── feat/ui-foundation
├── feat/ui-shell
├── feat/ui-jobs
├── feat/ui-dashboard-applications
├── feat/ui-profile-resume
├── feat/ui-settings
├── feat/ui-interaction
├── feat/desktop-window-chrome
├── chore/packaging-resources-layout
└── test/ui-e2e-visual
```

规则：

1. 子智能体禁止直接提交到 `main`；
2. 子智能体禁止直接提交到 `feat/ui-modernization`；
3. ORCH 是唯一合并者；
4. 每个 Wave 开始时，ORCH 发布该 Wave 的 **base SHA**；
5. 同一 Wave 的 Agent 必须从同一 base SHA 创建 branch；
6. Wave 合并完成后，下一 Wave 必须从新的 integration HEAD 开始；
7. 不允许长期 branch 跨越多个 Wave 后再“大合并”；
8. feature Agent 禁止自行 rebase/merge 其他 feature Agent 分支；
9. 冲突只由 ORCH 在 integration branch 处理；
10. 合并前每个 Agent 必须提供 commit SHA + 测试结果 + 修改路径 + 风险说明。

推荐工作方式：

```text
main
  ↓
feat/ui-modernization
  ↓ Wave base SHA
多个 worktree 并行
  ↓
ORCH review / merge
  ↓
新的 Wave base SHA
```

---

## 30.3 共享文件所有权（Conflict Budget）

以下文件/目录属于高冲突区域，必须设唯一 Owner。

### UI-FOUNDATION 独占

```text
apps/desktop/package.json
apps/desktop/vite.config.ts
根 package manifest / lockfile（如因前端依赖发生变化）
apps/desktop/src/styles/tokens.css
apps/desktop/src/components/ui/**
apps/desktop/src/lib/cn* / utils*（样式工具）
shadcn 配置文件
Tailwind 入口配置
```

其他 Agent **不得自行安装 npm 依赖**。如果需要新依赖，必须向 ORCH 提交依赖请求，由 UI-FOUNDATION 或 ORCH 集中处理。

### UI-SHELL 独占

```text
apps/desktop/src/components/AppShell.tsx
apps/desktop/src/components/desktop-kit/app-sidebar.tsx
apps/desktop/src/components/desktop-kit/page-header.tsx
apps/desktop/src/components/desktop-kit/panel-shell.tsx
apps/desktop/src/app/routes.tsx（如确需调整）
```

Wave 2 合并后，以上公共 Shell API 视为冻结。

### Feature Agent 各自独占

```text
UI-JOBS:
  apps/desktop/src/features/jobs/**
  apps/desktop/src/pages/JobsPage.tsx
  对应 jobs UI tests

UI-DA:
  apps/desktop/src/features/dashboard/**
  apps/desktop/src/features/applications/**
  apps/desktop/src/pages/DashboardPage.tsx
  apps/desktop/src/pages/ApplicationsPage.tsx
  对应 tests

UI-PR:
  apps/desktop/src/features/profile/**
  apps/desktop/src/features/resumes/**
  apps/desktop/src/pages/ProfilePage.tsx
  apps/desktop/src/pages/ResumesPage.tsx
  对应 tests

UI-SETTINGS:
  apps/desktop/src/features/settings/**
  apps/desktop/src/components/settings-kit/**
  apps/desktop/src/pages/SettingsPage.tsx
  对应 tests
```

### DESKTOP 独占

```text
apps/desktop/src-tauri/**
apps/desktop/src/components/window-chrome/**
安装 / NSIS / sidecar packaging 相关 scripts
```

注意：`tauri.conf.json` 与 Rust `main.rs` 同时会被 Window Chrome 和 Packaging 使用，因此这两项**不允许并行写同一文件**，见 Wave 4/5 顺序。

### QA 独占

```text
e2e/**
playwright*.config.*
视觉回归 fixture / screenshot baseline
独立的 smoke / benchmark 测试文件
```

QA 不应为了让测试通过而修改业务实现；发现实现缺陷时回报 ORCH，由对应 Owner 修复。

---

## 30.4 公共契约冻结点

并行 feature 开始前，ORCH 必须确认以下契约已冻结：

### Freeze A — UI Primitive Contract

至少确定：

```text
Button
Badge
Card
Input
Select
Dialog
Tooltip
Dropdown
Tabs
Sheet
Skeleton
Separator
Switch
Progress
Toast
```

包括：

- export path；
- variant；
- size；
- token 命名；
- `cn()` 使用方式。

Freeze A 后，feature Agent 不允许自己复制一套 primitive。

### Freeze B — Desktop Kit Contract

至少确定：

```text
AppSidebar
PageHeader
PanelShell
EmptyState
StatusIndicator
InspectorPanel
```

Freeze B 后，Wave 3 feature Agent 可以并行。

### Freeze C — Domain/API Contract

UI 项目继续复用现有 API client。

明确：

- Job status 枚举不因 UI 改名；
- Application SSOT 不变；
- Profile confirmed 语义不变；
- Resume Draft 状态不变；
- Core auth wrapper 不变；
- session token 不变。

任何 Agent 发现 API 缺失，只能记录“API gap”，不得为了 UI 直接私自改变后端语义。

---

# 30.5 Wave 0 — ORCH + QA 并行：基线冻结

**可并行 Agent：ORCH、QA**

### ORCH

任务：

- 建立 `feat/ui-modernization`；
- 记录 main SHA；
- 跑现有 test/build；
- 记录当前 API / route / security invariant；
- 输出 Wave 1 base SHA；
- 建立文件 Owner 表。

### QA

任务：

- 记录现有页面截图；
- 记录 1024×700 / 1280×820 / 1440×900 当前表现；
- 记录 Light 当前基线；
- 记录 installer 目录树；
- 建立最小 smoke checklist；
- 不修改业务代码。

### Gate 0

必须同时满足：

- baseline test 结果已记录；
- baseline screenshot 已记录；
- installer layout 已记录；
- integration branch 可构建。

Gate 0 通过后才进入 Wave 1。

---

# 30.6 Wave 1 — UI-FOUNDATION：共享底座串行完成

**本 Wave 不建议多个 Agent 同时改前端共享底座。**

负责人：`UI-FOUNDATION`

任务：

- Tailwind CSS；
- `@tailwindcss/vite`；
- Design Token；
- shadcn / Base UI；
- Lucide；
- CVA / clsx / tailwind-merge；
- 必要表单依赖；
- UI primitive；
- Light / Dark token 基础；
- primitive unit tests。

可以由 QA 同时**只读审查**和准备测试，但不得写共享前端文件。

### Gate 1 / Freeze A

ORCH 审查：

- primitive API；
- token；
- dependency；
- build；
- unit test。

通过后合入 integration，并发布 Wave 2 base SHA。

---

# 30.7 Wave 2 — UI-SHELL + QA 并行

**可并行 Agent：UI-SHELL、QA**

### UI-SHELL

任务：

- AppShell；
- Sidebar inset；
- Sidebar collapse；
- Lucide 导航；
- PageHeader；
- PanelShell；
- EmptyState；
- StatusIndicator；
- CoreFailureBanner 保留；
- Desktop Kit 基础；
- 1024px 最小窗口。

### QA

基于 Freeze A：

- primitive interaction tests；
- Sidebar 预期测试草案；
- keyboard / focus checklist；
- 不修改 Shell 实现。

### Gate 2 / Freeze B

ORCH 必须确认：

- 六个一级路由均正常；
- Sidebar active/collapse 正确；
- Core Error 可见；
- desktop-kit API 稳定；
- 不存在旧/新两套 Shell。

合并后发布 Wave 3 base SHA。

---

# 30.8 Wave 3 — 业务页面最大并行波次

这是并行收益最大的阶段。

**四个 Agent 可同时执行：**

```text
UI-JOBS
UI-DA
UI-PR
UI-SETTINGS
```

四者必须从同一个 Wave 3 base SHA 开始。

## UI-JOBS

负责：

- 高密度 Job 列表；
- `@tanstack/react-virtual`；
- Job Inspector；
- filters；
- search；
- status badges；
- Data Source Popover；
- loading / empty / error；
- verified gate；
- Job 页面测试。

禁止：

- 修改 Job 后端状态含义；
- 修改 Core client auth；
- 把未验证 Job 变成可申请。

## UI-DA

负责 Dashboard + Applications：

Dashboard：

- 真实数据布局；
- 今日状态；
- 求职进度；
- 今日建议；
- 数据源摘要。

Applications：

- 状态 tabs；
- 高密度列表；
- Application detail；
- Browser Agent progress surface（只接现有状态，不虚构后端状态）；
- Human Confirm Gate UI 不得绕过。

## UI-PR

负责 Profile + Resume：

Profile：

- 完整度；
- section；
- confirmed source；
- Draft Review；
- history surface。

Resume：

- immutable version list；
- SHA/version/status；
- OCR_REQUIRED；
- FAILED；
- selected detail；
- draft count。

硬约束：

- Resume import 不自动写 Profile；
- Draft 必须 accept/reject；
- Browser Agent 只读 confirmed data。

## UI-SETTINGS

负责：

- settings-kit；
- General；
- Appearance；
- AI Provider；
- Data Sources；
- Local Data；
- Browser Automation；
- About；
- form / validation UI；
- secret 不回显。

### Wave 3 冲突规则

Feature Agent 如果发现缺一个共享组件：

1. 不直接修改 `components/ui/**`；
2. 在结果中写 `Shared UI Request`；
3. ORCH 判断：
   - 可以 feature-local：先 feature-local；
   - 应成为共享组件：由 UI-FOUNDATION 小修补或 ORCH 单独提交；
4. 再让 feature Agent 基于补丁继续。

### Gate 3

ORCH 按顺序合并，推荐：

```text
UI-DA
→ UI-PR
→ UI-SETTINGS
→ UI-JOBS
```

Jobs 最后合并是因为其桌面交互复杂度和共享组件需求最高。

每次合并后：

- frontend unit；
- TypeScript build；
- Core tests（确保无越界）；
- 至少一轮 smoke。

全部通过后发布 Wave 4 base SHA。

---

# 30.9 Wave 4 — UI Interaction + Window Chrome 并行

建议拆出两个 Agent：

```text
UI-INTERACTION
DESKTOP-WINDOW
```

两者可并行，但文件边界必须严格。

## UI-INTERACTION

只负责前端：

- Light / Dark / System；
- Command Palette；
- Ctrl+K；
- keyboard navigation；
- Context Menu；
- Toast integration；
- focus restoration；
- reduced motion；
- accessibility polish。

不得修改 `src-tauri/**`。

## DESKTOP-WINDOW

只负责：

- Tauri Custom Titlebar；
- drag region；
- minimize；
- maximize / restore；
- close；
- Windows DPI；
- safe area；
- Window Chrome tests / manual checklist。

不得修改 feature 页面。

### Gate 4

ORCH 合并并验证：

- 主题；
- keyboard；
- titlebar；
- 100/125/150% DPI；
- Window controls；
- 现有业务 smoke。

---

# 30.10 Wave 5 — Packaging Cleanup 串行 + QA 并行

负责人：

```text
DESKTOP-PACKAGING
QA
```

DESKTOP-PACKAGING 必须基于已经合入 Window Chrome 的新 base SHA，因为它可能继续修改：

```text
tauri.conf.json
src-tauri/src/main.rs
packaging scripts
```

任务：

- `core-api/` → `resources/core-api/`；
- Rust lookup；
- 可选旧路径兼容；
- NSIS resource；
- installer smoke；
- sidecar health/auth；
- uninstall；
- process cleanup。

QA 并行：

- 安装前后目录 diff；
- GUI smoke；
- sidecar orphan 检查；
- fresh profile install；
- uninstall 保留用户数据策略确认。

### Gate 5

必须满足：

```text
<install>/
├── xiaoyue-job-search.exe
├── uninstall.exe
└── resources/
    └── core-api/
```

且：

- Core 启动；
- health 200；
- auth 正常；
- app 退出无 sidecar；
- uninstall 成功。

---

# 30.11 Wave 6 — QA / E2E / Visual 最终并行验证

最后由 QA 主导，同时允许各 feature Owner 只修自己领域的问题。

测试并行分组：

### QA-A：Functional E2E

```text
启动
→ 首页
→ 岗位雷达
→ 筛选
→ Inspector
→ Profile
→ Resume
→ Settings
→ Application
```

### QA-B：Visual Regression

矩阵：

```text
1024×700
1280×820
1440×900

× Light / Dark
× Sidebar expand / collapse
```

### QA-C：A11y / Keyboard

- Tab；
- Shift+Tab；
- Enter；
- Escape；
- Focus restore；
- Dialog/Sheet trap；
- reduced motion；
- forced colors 基础。

### QA-D：Performance

- 1k jobs；
- 10k synthetic jobs；
- virtual list DOM 数；
- Sidebar rerender；
- initial render；
- bundle size。

### QA-E：Packaging / Runtime

- clean install；
- upgrade install（如当前 release 流程支持）；
- launch；
- sidecar；
- exit；
- uninstall。

---

# 30.12 主智能体 ORCH 的职责

ORCH **不要亲自承担大面积 feature 编码**，否则会成为并行瓶颈。

ORCH 只负责：

1. 给每个 Wave 发布 base SHA；
2. 创建/指定 branch；
3. 明确文件 ownership；
4. 冻结共享契约；
5. 处理 Shared UI Request；
6. 审核子智能体 commit；
7. 合并；
8. 处理冲突；
9. 跑 Gate；
10. 发现回归时把问题退回对应 Owner；
11. 保证安全 invariant；
12. 最后合并 `feat/ui-modernization` → `main`。

ORCH 不允许：

- 为了赶进度绕过 test；
- 让两个 Agent 同时改高冲突文件；
- 让 Agent 直接 merge main；
- 在 Gate 未通过时开启下一依赖 Wave；
- 用大面积 conflict resolution 掩盖设计冲突。

---

# 30.13 子智能体统一任务模板

主智能体发给每个子智能体的任务必须至少包含：

```text
Role:
<UI-JOBS / UI-PR / ...>

Base SHA:
<明确 commit SHA>

Branch:
<明确 branch>

Owned paths:
<允许修改的路径>

Read-only paths:
<可阅读但禁止修改>

Forbidden paths:
<禁止修改>

Dependencies / Frozen contracts:
<Freeze A / B / C>

Tasks:
1.
2.
3.

Must preserve:
- security invariant
- API semantics
- confirmed Profile semantics
- verified Job gate
...

Required tests:
<具体命令>

Deliverables:
- commit SHA
- changed files
- test result
- screenshots if applicable
- known risks
- Shared UI Requests
```

禁止只给一句“把某页面美化一下”。

---

# 30.14 子智能体回报格式

每个子智能体结束时必须回报：

```text
STATUS: READY_TO_MERGE | BLOCKED | NEEDS_SHARED_CHANGE

BASE_SHA:
BRANCH:
HEAD_SHA:

CHANGED_PATHS:
- ...

TESTS:
- command: PASS/FAIL

BEHAVIORAL_CHANGES:
- ...

INVARIANTS_CHECKED:
- ...

SHARED_UI_REQUESTS:
- ...

KNOWN_RISKS:
- ...

SCREENSHOTS:
- ...
```

ORCH 只有在 `READY_TO_MERGE` 且测试通过时才允许合并。

---

# 30.15 并行依赖图

```text
Wave 0
ORCH ───────────────┐
QA baseline ────────┘
         │
         ▼
Wave 1
UI-FOUNDATION
         │
   Freeze A
         ▼
Wave 2
UI-SHELL  ║  QA
         │
   Freeze B/C
         ▼
Wave 3
┌────────────┬────────────┬────────────┬────────────┐
│ UI-JOBS    │ UI-DA      │ UI-PR      │ UI-SETTINGS│
└────────────┴────────────┴────────────┴────────────┘
         │
         ▼
Wave 4
UI-INTERACTION  ║  DESKTOP-WINDOW
         │
         ▼
Wave 5
DESKTOP-PACKAGING  ║  QA packaging
         │
         ▼
Wave 6
Functional E2E
Visual Regression
A11y
Performance
Packaging Runtime
         │
         ▼
ORCH Final Gate
         │
         ▼
feat/ui-modernization → main
```

---

# 30.16 最大并发建议

推荐并发上限：

```text
Wave 0: 2
Wave 1: 1
Wave 2: 2
Wave 3: 4
Wave 4: 2
Wave 5: 2
Wave 6: 4~5（以测试任务为主）
```

不要为了“子智能体越多越快”把一个页面拆成多个 Agent 同时改。

最适合并行的是**不同 feature 目录**，最不适合并行的是：

- package / lockfile；
- Design Token；
- primitive；
- AppShell；
- routes；
- global styles；
- tauri.conf；
- Rust main；
- installer scripts。

---

# 30.17 失败与回滚策略

任何 Wave 出现以下情况必须停止向后推进：

- production build fail；
- TypeScript fail；
- Core test regression；
- session auth regression；
- Job verified gate regression；
- Profile confirmed semantics regression；
- installer smoke regression；
- sidecar orphan；
- 主导航不可用。

处理方式：

1. ORCH 定位 Owner；
2. Owner 在自己的 branch 修复；
3. 不允许下一个 Wave 用 workaround 掩盖；
4. 修复后重新跑 Gate；
5. 仍失败则 revert 对应 Agent merge，不回滚其他已通过的独立 Agent。

---

# 30.18 最终集成顺序

最终不是“所有 Agent 一次性合并”，而是：

```text
Foundation
→ Shell
→ Dashboard/Applications
→ Profile/Resume
→ Settings
→ Jobs
→ Interaction
→ Window Chrome
→ Packaging
→ QA/E2E
```

每一步保持 integration branch 始终可构建、可测试、可回滚。

---

# 31. 推荐提交拆分

建议至少：

```text
feat(ui): add tailwind and design tokens
feat(ui): add shared primitives
feat(ui): add desktop shell and sidebar
feat(ui): migrate dashboard
feat(ui): migrate job radar
feat(ui): add virtualized jobs inspector
feat(ui): migrate applications
feat(ui): migrate profile
feat(ui): migrate resume vault
feat(ui): migrate settings
feat(ui): add themes and reduced motion
feat(ui): add command palette
feat(desktop): add custom window chrome
chore(packaging): move core sidecar under resources
test(ui): add desktop e2e and visual regression
```

不要做一个超大 commit。

---

# 32. Definition of Done

本方案完成时必须满足：

- [ ] Tauri 2 保留；
- [ ] FastAPI sidecar 保留；
- [ ] PyInstaller onedir 保留；
- [ ] React 19 保留；
- [ ] Tailwind / Design Token 完成；
- [ ] shadcn/Base UI primitive 完成；
- [ ] desktop-kit 完成；
- [ ] Sidebar inset 完成；
- [ ] Sidebar 可折叠；
- [ ] Dashboard 完成；
- [ ] Jobs 高密度列表完成；
- [ ] Jobs virtual list 完成；
- [ ] Job Inspector 完成；
- [ ] Applications 完成；
- [ ] Profile 完成；
- [ ] Resume Vault 完成；
- [ ] Settings 完成；
- [ ] Light/Dark/System 完成；
- [ ] Reduced Motion 完成；
- [ ] Command Palette 完成；
- [ ] Custom Window Chrome 完成或有单独延期说明；
- [ ] Installer 目录整理完成；
- [ ] sidecar smoke 通过；
- [ ] frontend tests 通过；
- [ ] core tests 通过；
- [ ] cargo tests 通过；
- [ ] production build 通过；
- [ ] tauri build 通过；
- [ ] installer smoke 通过；
- [ ] 无业务安全语义回退。

---

# 33. 最终目标技术形态

```text
             小悦求职
                 │
        ┌────────┴────────┐
        │                 │
   UI / Desktop       Business Core
        │                 │
 React 19          Python / FastAPI
 TypeScript        SQLAlchemy
 Tailwind 4        SQLite
 shadcn/ui         AI Provider
 Base UI           Browser Agent
 Lucide            Resume Parser
        │                 │
        └────────┬────────┘
                 │
               Tauri 2
                 │
               Rust
                 │
              Windows
```

本次升级最终应让小悦同时具备：

- Motrix 一类现代桌面应用的 UI 工程组织；
- Tauri 的轻量桌面壳；
- Rust 的桌面边界；
- Python 的 AI / Browser Automation 生态；
- 现有 Profile / Resume / Job / Application 安全数据链。

核心结论：

> **不要照搬 Motrix 的 Electron；只借鉴它成熟的前端 UI 架构与桌面交互设计。**
