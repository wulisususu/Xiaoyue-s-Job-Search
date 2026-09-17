import { useCallback, useEffect, useState } from 'react';

import { ApplicationRecord, getApplications, updateApplicationStatus } from '../api/applicationsClient';

const statusLabel: Record<string, string> = {
  OPENED: '已打开入口',
  IN_PROGRESS: '填写中',
  SUBMITTED: '已投递',
  INTERVIEWING: '面试中',
  OFFER: 'Offer',
  REJECTED: '已拒绝',
  ABANDONED: '已放弃',
};

const statusOptions = ['OPENED', 'IN_PROGRESS', 'SUBMITTED', 'INTERVIEWING', 'OFFER', 'REJECTED', 'ABANDONED'];

export function ApplicationsPage() {
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const refresh = useCallback(() => {
    setLoading(true);
    setError('');
    getApplications()
      .then(setApplications)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : '投递记录加载失败'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function changeStatus(id: number, status: string) {
    setUpdatingId(id);
    try {
      const updated = await updateApplicationStatus(id, status);
      setApplications((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '状态更新失败');
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">CRM</p>
          <h1>投递中心</h1>
          <p>记录每一次申请、使用的简历版本与后续进展。Browser Agent 完成后，自动投递会以相同的时间线写入这里。</p>
        </div>
      </header>

      {loading && <article className="empty-panel"><p>正在读取投递记录…</p></article>}
      {error && <article className="empty-panel"><h2>投递记录加载失败</h2><p>{error}</p></article>}
      {!loading && !error && applications.length === 0 && (
        <article className="empty-panel">
          <h2>暂无投递记录</h2>
          <p>在岗位雷达中验证入口后点击"开始申请"，这里会出现第一条记录。</p>
        </article>
      )}

      {!loading && !error && applications.length > 0 && (
        <div className="job-list">
          {applications.map((application) => (
            <article className="job-card" key={application.id}>
              <div className="job-card-main">
                <div className="badge-row">
                  <span className="soft-badge verified">{statusLabel[application.status] ?? application.status}</span>
                  <span className="soft-badge">{application.channel === 'manual' ? '手动投递' : application.channel}</span>
                </div>
                <h2>{application.company_name}</h2>
                <h3>{application.job_title}</h3>
                <p className="job-verification">开始时间：{formatTime(application.opened_at)} · 最近更新：{formatTime(application.updated_at)}</p>
                {application.opened_url && <p className="job-source">入口：{application.opened_url}</p>}
              </div>
              <div className="job-actions">
                <select
                  aria-label="投递状态"
                  value={application.status}
                  disabled={updatingId === application.id}
                  onChange={(event) => changeStatus(application.id, event.target.value)}
                >
                  {statusOptions.map((option) => (
                    <option key={option} value={option}>{statusLabel[option] ?? option}</option>
                  ))}
                </select>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function formatTime(value: string | null) {
  if (!value) return '未知';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}
