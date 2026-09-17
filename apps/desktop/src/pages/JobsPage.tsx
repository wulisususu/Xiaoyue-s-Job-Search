import { FormEvent, useCallback, useEffect, useState } from 'react';

import {
  getJobStats,
  getJobs,
  getSourceStatus,
  JobFilters,
  JobStats,
  RadarJob,
  runDueVerification,
  SourceStatus,
  syncDueSources,
  syncTencentSource,
  syncWorkfindSource,
  verifyJob,
} from '../api/jobsClient';
import { startApplication } from '../api/applicationsClient';

const emptyStats: JobStats = {
  total: 0,
  with_url_unverified: 0,
  without_url: 0,
  verified_open: 0,
  rediscovery_required: 0,
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
  REDISCOVERY_REQUIRED: '入口失效待重发现',
  STALE: '上游已失效',
  REQUIRES_BROWSER: '需浏览器复核',
};

const atsLabel: Record<string, string> = {
  moka: 'Moka',
  beisen: '北森',
  hotjob: 'Hotjob',
  feishu: '飞书招聘',
  lark: '飞书招聘',
  job51: '51job',
  guopin: '国聘',
  successfactors: 'SAP SuccessFactors',
};

const sourceNames: Record<string, string> = {
  'tencent-sheet': '腾讯文档',
  'workfind-online': 'WorkFind',
};

const sourceStateLabels: Record<string, string> = {
  SUCCESS: '正常',
  UNCHANGED: '已是最新',
  FAILED: '同步失败',
};

const PAGE_SIZE = 50;

export function JobsPage() {
  const [jobs, setJobs] = useState<RadarJob[]>([]);
  const [stats, setStats] = useState<JobStats>(emptyStats);
  const [sources, setSources] = useState<SourceStatus[]>([]);
  const [filters, setFilters] = useState<JobFilters>({});
  const [draft, setDraft] = useState<JobFilters>({});
  const [page, setPage] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [actionKey, setActionKey] = useState('');
  const [actionMessage, setActionMessage] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(() => setRefreshKey((value) => value + 1), []);

  useEffect(() => {
    syncDueSources().then(refresh).catch(() => undefined);
  }, [refresh]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    Promise.all([getJobs({ ...filters, limit: PAGE_SIZE, offset: page * PAGE_SIZE }), getJobStats(), getSourceStatus()])
      .then(([jobData, statData, sourceData]) => {
        if (!active) return;
        setJobs(jobData.items);
        setTotal(jobData.total);
        setStats(statData);
        setSources(sourceData);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '岗位数据加载失败');
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [filters, page, refreshKey]);

  function submitFilters(event: FormEvent) {
    event.preventDefault();
    setPage(0);
    setFilters({ ...draft });
  }

  async function runAction(key: string, action: () => Promise<unknown>, successMessage: string) {
    setActionKey(key);
    setActionMessage('');
    try {
      await action();
      setActionMessage(successMessage);
      refresh();
    } catch (reason: unknown) {
      setActionMessage(reason instanceof Error ? reason.message : '操作失败');
    } finally {
      setActionKey('');
    }
  }

  async function beginApplication(job: RadarJob) {
    const url = job.canonical_url || job.apply_url;
    if (!url) return;
    setActionKey(`apply-${job.id}`);
    setActionMessage('');
    try {
      // Record the manual application session first; if the API is down we
      // still open the URL but surface the failure honestly.
      const record = await startApplication(job.id);
      window.open(record.opened_url || url, '_blank', 'noreferrer');
      setActionMessage('已记录申请会话，正在打开投递入口');
      refresh();
    } catch (reason: unknown) {
      setActionMessage(reason instanceof Error ? reason.message : '申请会话记录失败');
      window.open(url, '_blank', 'noreferrer');
    } finally {
      setActionKey('');
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Jobs</p>
          <h1>岗位雷达</h1>
          <p>腾讯文档与 WorkFind 负责发现，Xiaoyue 自己验证当前入口、ATS 和可申请状态。</p>
        </div>
      </header>

      <section className="source-health-panel" aria-label="在线数据源">
        <div className="source-health-header">
          <div>
            <h2>在线数据源</h2>
            <p>同步失败不会删除最后一次可用快照；原始来源 URL 也不会被验证结果覆盖。</p>
          </div>
          <div className="source-actions">
            <button className="secondary-button" type="button" disabled={Boolean(actionKey)} onClick={() => runAction('sync-tencent', syncTencentSource, '腾讯文档同步完成')}>
              {actionKey === 'sync-tencent' ? '同步中…' : '同步腾讯文档'}
            </button>
            <button className="secondary-button" type="button" disabled={Boolean(actionKey)} onClick={() => runAction('sync-workfind', syncWorkfindSource, 'WorkFind 同步完成')}>
              {actionKey === 'sync-workfind' ? '同步中…' : '同步 WorkFind'}
            </button>
            <button className="primary-button" type="button" disabled={Boolean(actionKey)} onClick={() => runAction('verify-due', () => runDueVerification(50), '到期入口验证完成')}>
              {actionKey === 'verify-due' ? '验证中…' : '验证到期入口'}
            </button>
          </div>
        </div>
        <div className="source-health-grid">
          {sources.map((source) => (
            <article className="source-health-card" key={source.source_name}>
              <div>
                <strong>{sourceNames[source.source_name] ?? source.source_name}</strong>
                <span className={`source-health-state ${source.last_run_status === 'FAILED' ? 'failed' : 'ok'}`}>
                  {source.last_run_status ? sourceStateLabels[source.last_run_status] ?? source.last_run_status : '未同步'}
                </span>
              </div>
              <p>最后同步：{formatTime(source.last_run_at)}</p>
              <p>可用版本：{source.last_good_version ?? '暂无'}</p>
              {source.last_error && <p className="source-error">{source.last_error}</p>}
            </article>
          ))}
        </div>
        {actionMessage && <p className="action-message" role="status">{actionMessage}</p>}
      </section>

      <div className="radar-stat-grid">
        <Stat label="全部岗位" value={stats.total} />
        <Stat label="已验证可申请" value={stats.verified_open} />
        <Stat label="有入口待验证" value={stats.with_url_unverified} />
        <Stat label="待重发现" value={stats.rediscovery_required} />
        <Stat label="无申请入口" value={stats.without_url} />
        <Stat label="央企关联" value={stats.central_soe} />
      </div>

      <form className="job-filters" onSubmit={submitFilters}>
        <input aria-label="搜索公司或岗位" placeholder="搜索公司或岗位" value={draft.q ?? ''} onChange={(event) => setDraft((current) => ({ ...current, q: event.target.value }))} />
        <select aria-label="企业性质" value={draft.ownership ?? ''} onChange={(event) => setDraft((current) => ({ ...current, ownership: event.target.value || undefined }))}>
          <option value="">全部企业性质</option><option value="central_soe">央企</option><option value="local_soe">地方国企</option><option value="unknown">待识别</option>
        </select>
        <select aria-label="入口状态" value={draft.status ?? ''} onChange={(event) => setDraft((current) => ({ ...current, status: event.target.value || undefined }))}>
          <option value="">全部入口状态</option><option value="VERIFIED_OPEN">已验证可申请</option><option value="DISCOVERED_URL_UNVERIFIED">有入口待验证</option><option value="REDISCOVERY_REQUIRED">入口失效待重发现</option><option value="DISCOVERED_NO_URL">无申请入口</option>
        </select>
        <input aria-label="工作地点" placeholder="工作地点" value={draft.location ?? ''} onChange={(event) => setDraft((current) => ({ ...current, location: event.target.value }))} />
        <button className="primary-button" type="submit">筛选</button>
      </form>

      {loading && <article className="empty-panel"><p>正在读取本地岗位库…</p></article>}
      {error && <article className="empty-panel"><h2>岗位数据加载失败</h2><p>{error}</p></article>}
      {!loading && !error && jobs.length === 0 && <article className="empty-panel"><h2>暂无匹配岗位</h2><p>先同步在线数据源，或调整筛选条件。</p></article>}

      {!loading && !error && jobs.length > 0 && (
        <div className="job-list">
          {jobs.map((job) => {
            const verified = job.status === 'VERIFIED_OPEN';
            const canVerify = Boolean(job.apply_url) && !verified;
            return (
              <article className="job-card" key={job.id}>
                <div className="job-card-main">
                  <div className="job-card-heading">
                    <div>
                      <div className="badge-row">
                        <span className="soft-badge">{ownershipLabel[job.company.ownership] ?? job.company.ownership}</span>
                        <span className={`soft-badge ${verified ? 'verified' : 'warning'}`}>{statusLabel[job.status] ?? job.status}</span>
                        {job.ats && <span className="soft-badge ats-badge">{atsLabel[job.ats] ?? job.ats}</span>}
                      </div>
                      <h2>{job.company.name}</h2><h3>{job.title}</h3>
                    </div>
                    <span className="source-date">数据 {job.source_updated_at ?? '未知日期'}</span>
                  </div>
                  <div className="job-meta"><span>{job.location || '地点未注明'}</span><span>{job.industry || '行业未注明'}</span><span>{job.recruitment_batch || '批次未注明'}</span><span>{job.deadline_text || '截止时间未注明'}</span></div>
                  <p className="job-source">来源：{job.sources.join(' / ') || '未知来源'}</p>
                  {job.last_verified_at && <p className="job-verification">最近验证：{formatTime(job.last_verified_at)} · {job.verification_health ?? 'UNKNOWN'}</p>}
                </div>
                <div className="job-actions">
                  {job.apply_url ? <a href={job.apply_url} target="_blank" rel="noreferrer" className="secondary-button">查看原始入口</a> : <span className="muted-action">暂无入口</span>}
                  {canVerify && <button className="secondary-button" type="button" disabled={Boolean(actionKey)} onClick={() => runAction(`verify-${job.id}`, () => verifyJob(job.id), '入口验证完成')}>{actionKey === `verify-${job.id}` ? '验证中…' : '验证入口'}</button>}
                  <button className="primary-button" type="button" disabled={!verified} onClick={() => beginApplication(job)}>{actionKey === `apply-${job.id}` ? '打开中…' : '开始申请'}</button>
                </div>
              </article>
            );
          })}
        </div>
      )}

      {!loading && !error && total > 0 && (
        <nav className="job-pagination" aria-label="岗位分页">
          <button className="secondary-button" type="button" disabled={page === 0} onClick={() => setPage((value) => Math.max(0, value - 1))}>上一页</button>
          <span className="pagination-info">
            第 {page * PAGE_SIZE + 1}–{Math.min((page + 1) * PAGE_SIZE, total)} 条，共 {total} 条
          </span>
          <button className="secondary-button" type="button" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => setPage((value) => value + 1)}>下一页</button>
        </nav>
      )}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return <article className="radar-stat"><span>{label}</span><strong>{value}</strong></article>;
}

function formatTime(value: string | null) {
  if (!value) return '从未';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}
