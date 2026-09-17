import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, expect, it } from 'vitest';

import { AppShell } from './AppShell';

afterEach(() => {
  cleanup();
  delete (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__;
});

it('shows all primary navigation items', () => {
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  );

  for (const label of ['首页', '岗位雷达', '投递中心', '我的资料', '简历库', '设置']) {
    expect(screen.getByText(label)).toBeInTheDocument();
  }
});

it('shows a diagnostic banner when the core sidecar failed to start', () => {
  (window as unknown as Record<string, unknown>).__XIAOYUE_CORE_ERROR__ =
    'spawn 失败: 访问被拒绝 (os error 5)';
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  );

  const banner = screen.getByRole('alert');
  expect(banner).toHaveTextContent('本地核心服务启动失败');
  expect(banner).toHaveTextContent('访问被拒绝');
  expect(banner).toHaveTextContent('logs');
});

it('shows no banner when the core runtime is healthy', () => {
  render(
    <MemoryRouter>
      <AppShell />
    </MemoryRouter>,
  );

  expect(screen.queryByRole('alert')).not.toBeInTheDocument();
});
