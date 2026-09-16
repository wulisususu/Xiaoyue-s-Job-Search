import { Navigate, Route, Routes } from 'react-router-dom';

import { AppShell } from '../components/AppShell';
import { ApplicationsPage } from '../pages/ApplicationsPage';
import { DashboardPage } from '../pages/DashboardPage';
import { JobsPage } from '../pages/JobsPage';
import { ProfilePage } from '../pages/ProfilePage';
import { ResumesPage } from '../pages/ResumesPage';
import { SettingsPage } from '../pages/SettingsPage';

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardPage />} />
        <Route path="jobs" element={<JobsPage />} />
        <Route path="applications" element={<ApplicationsPage />} />
        <Route path="profile" element={<ProfilePage />} />
        <Route path="resumes" element={<ResumesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Route>
    </Routes>
  );
}
