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

# 30. 推荐提交拆分

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

# 31. Definition of Done

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

# 32. 最终目标技术形态

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
