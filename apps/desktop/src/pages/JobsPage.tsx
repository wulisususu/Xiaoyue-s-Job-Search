import { FormEvent, useEffect, useState } from 'react';

import { getJobStats, getJobs, JobFilters, JobStats, RadarJob } from '../api/jobsClient';

const emptyStats: JobStats = {
  total: 0,
  with_url_unverified: 0,
  without_url: 0,
  central_soe: 0,
  local_soe: 0,
  unknown: 0,
};

const ownershipLabel: Record<string, string> = {
  central_soe: '央企',
  local_soe: '地方国企',
  unknown: '待识别',
};

const statusLabel: Record<string, string> = {
  DISCOVERED_URL_UNVERIFIED: '入口待验证',
  DISCOVERED_NO_URL: '待补申请入口',
  VERIFIED_OPEN: '已验证可申请',
};

export function JobsPage() {
  const [jobs, setJobs] = useState<RadarJob[]>([]);
  const [stats, setStats] = useState<JobStats>(emptyStats);
  const [filters, setFilters] = useState<JobFilters>({});
  const [draft, setDraft] = useState<JobFilters>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([getJobs(filters), getJobStats()])
      .then(([jobData, statData]) => {
        if (!active) return;
        setJobs(jobData.items);
        setStats(statData);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '岗位数据加载失败');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [filters]);

  function submitFilters(event: FormEvent) {
    event.preventDefault();
    setFilters({ ...draft });
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Jobs</p>
          <h1>岗位雷达</h1>
          <p>WorkFind 企业主库 + Xiaozhao Radar 招聘事件流。当前入口仍需后续验证器确认。</p>
        </div>
      </header>

      <div className="radar-stat-grid">
        <Stat label="全部岗位" value={stats.total} />
        <Stat label="有入口待验证" value={stats.with_url_unverified} />
        <Stat label="无申请入口" value={stats.without_url} />
        <Stat label="央企关联" value={stats.central_soe} />
        <Stat label="地方国企" value={stats.local_soe} />
        <Stat label="待识别企业" value={stats.unknown} />
      </div>

      <form className="job-filters" onSubmit={submitFilters}>
        <input
          aria-label="搜索公司或岗位"
          placeholder="搜索公司或岗位"
          value={draft.q ?? ''}
          onChange={(event) => setDraft((current) => ({ ...current, q: event.target.value }))}
        />
        <select
          aria-label="企业性质"
          value={draft.ownership ?? ''}
          onChange={(event) => setDraft((current) => ({ ...current, ownership: event.target.value || undefined }))}
        >
          <option value="">全部企业性质</option>
          <option value="central_soe">央企</option>
          <option value="local_soe">地方国企</option>
          <option value="unknown">待识别</option>
        </select>
        <select
          aria-label="入口状态"
          value={draft.status ?? ''}
          onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value || undefined }))}
        >
          <option value="">全部入口状态</option>
          <option value="DISCOVERED_URL_UNVERIFIED">有入口待验证</option>
          <option value="DISCOVERED_NO_URL">无申请入口</option>
        </select>
        <input
          aria-label="工作地点"
          placeholder="工作地点"
          value={draft.location ?? ''}
          onChange={(event) => setDraft((current) => ({ ...current, location: event.target.value }))}
        />
        <button className="primary-button" type="submit">筛选</button>
      </form>

      {loading && <article className="empty-panel"><p>正在读取本地岗位库…</p></article>}
      {error && <article className="empty-panel"><h2>岗位数据加载失败</h2><p>{error}</p></article>}
      {!loading && !error && jobs.length === 0 && (
        <article className="empty-panel"><h2>暂无匹配岗位</h2><p>先运行数据导入命令，或调整筛选条件。</p></article>
      )}

      {!loading && !error && jobs.length > 0 && (
        <div className="job-list">
          {jobs.map((job) => {
            const verified = job.status === 'VERIFIED_OPEN';
            return (
              <article className="job-card" key={job.id}>
                <div className="job-card-main">
                  <div className="job-card-heading">
                    <div>
                      <div className="badge-row">
                        <span className="soft-badge">{ownershipLabel[job.company.ownership] ?? job.company.ownership}</span>
                        <span className={`soft-badge ${verified ? 'verified' : 'warning'}`}>
                          {statusLabel[job.status] ?? job.status}
                        </span>
                      </div>
                      <h2>{job.company.name}</h2>
                      <h3>{job.title}</h3>
                    </div>
                    <span className="source-date">数据 {job.source_updated_at ?? '未知日期'}</span>
                  </div>
                  <div className="job-meta">
                    <span>{job.location || '地点未注明'}</span>
                    <span>{job.industry || '行业未注明'}</span>
                    <span>{job.recruitment_batch || '批次未注明'}</span>
                    <span>{job.deadline_text || '截止时间未注明'}</span>
                  </div>
                  <p className="job-source">来源：{job.sources.join(' / ') || '未知来源'}</p>
                </div>
                <div className="job-actions">
                  {job.apply_url ? (
                    <a href={job.apply_url} target="_blank" rel="noreferrer" className="secondary-button">查看原始入口</a>
                  ) : (
                    <span className="muted-action">暂无入口</span>
                  )}
                  <button className="primary-button" type="button" disabled={!verified}>开始申请</button>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <article className="radar-stat"><span>{label}</span><strong>{value}</strong></article>;
}
