import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { expect, it } from 'vitest';

import { AppShell } from './AppShell';

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
