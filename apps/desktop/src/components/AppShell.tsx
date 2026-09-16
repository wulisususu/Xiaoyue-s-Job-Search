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
      <main className="main-content"><Outlet /></main>
    </div>
  );
}
