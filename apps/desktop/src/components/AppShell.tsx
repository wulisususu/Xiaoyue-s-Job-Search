import { NavLink, Outlet } from 'react-router-dom';

const navItems = [
  { to: '/', label: '首页', end: true },
  { to: '/jobs', label: '岗位雷达' },
  { to: '/applications', label: '投递中心' },
  { to: '/profile', label: '我的资料' },
  { to: '/resumes', label: '简历库' },
  { to: '/settings', label: '设置' },
] as const;

export function AppShell() {
  const coreError =
    typeof window !== 'undefined'
      ? (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__
      : undefined;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-mark">悦</span>
          <div>
            <strong>小悦求职</strong>
            <span>央国企 AI 求职工作台</span>
          </div>
        </div>
        <nav aria-label="主导航" className="navigation">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={'end' in item ? item.end : false}
              className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">Local-first · V0.1</div>
      </aside>
      <main className="main-content">
        {typeof coreError === 'string' && coreError !== '' && (
          <div role="alert" className="core-error-banner">
            <strong>本地核心服务启动失败</strong>
            <div>岗位、资料、简历等功能依赖本地 Core 服务，当前不可用。</div>
            <div>原因：{coreError}</div>
            <div>请在应用数据目录 logs/ 下查看 core-*.log（每次启动一对文件），重启应用后重试。</div>
          </div>
        )}
        <Outlet />
      </main>
    </div>
  );
}
