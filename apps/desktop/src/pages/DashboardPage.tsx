import { useEffect, useMemo, useState } from 'react';

import { getCoreHealth } from '../api/coreClient';
import { getDashboardSummary, type DashboardSummary } from '../api/dashboardClient';

export function DashboardPage() {
  const [coreConnected, setCoreConnected] = useState<boolean | null>(null);
  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let mounted = true;
    getCoreHealth()
      .then(() => mounted && setCoreConnected(true))
      .catch(() => mounted && setCoreConnected(false));
    getDashboardSummary()
      .then((data) => mounted && setSummary(data))
      .catch((reason: unknown) => {
        if (mounted) setError(reason instanceof Error ? reason.message : 'Dashboard 数据加载失败');
      });
    return () => {
      mounted = false;
    };
  }, []);

  const metrics = useMemo(
    () => [
      ['今日新增岗位', summary?.new_jobs_today],
      ['可申请岗位', summary?.verified_open],
      ['央企岗位', summary?.central_soe_jobs],
      ['岗位总数', summary?.total_jobs],
      ['填写中', summary?.in_progress],
      ['已投递', summary?.submitted],
      ['面试中', summary?.interviewing],
      ['Offer', summary?.offers],
    ] as const,
    [summary],
  );

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Dashboard</p>
          <h1>首页</h1>
          <p>岗位池、网申进度与本地工作台的实时概览。</p>
        </div>
        <span className={`status-pill ${coreConnected ? 'online' : ''}`}>
          本地核心：{coreConnected === null ? '检测中' : coreConnected ? '已连接' : '未连接'}
        </span>
      </header>

      <div className="metric-grid">
        {metrics.map(([label, value]) => (
          <article className="metric-card" key={label}>
            <span>{label}</span>
            <strong>{value ?? '—'}</strong>
          </article>
        ))}
      </div>

      <DashboardGuidance summary={summary} error={error} />
    </section>
  );
}

function DashboardGuidance({
  summary,
  error,
}: {
  summary: DashboardSummary | null;
  error: string;
}) {
  if (error) {
    return (
      <article className="empty-panel">
        <h2>工作台数据暂不可用</h2>
        <p>{error}</p>
      </article>
    );
  }

  if (!summary) {
    return (
      <article className="empty-panel">
        <h2>正在读取工作台</h2>
        <p>正在汇总岗位池和投递进度。</p>
      </article>
    );
  }

  if (summary.total_jobs === 0) {
    return (
      <article className="empty-panel">
        <h2>先同步岗位数据源</h2>
        <p>岗位雷达已支持腾讯文档与 WorkFind；同步完成后，这里会显示真实岗位和投递漏斗。</p>
      </article>
    );
  }

  if (summary.verified_open === 0) {
    return (
      <article className="empty-panel">
        <h2>岗位已入库，下一步验证申请入口</h2>
        <p>验证后的真实申请入口会进入“可申请岗位”，再交给手动申请或 Browser Agent。</p>
      </article>
    );
  }

  if (summary.applications_total === 0) {
    return (
      <article className="empty-panel">
        <h2>岗位已准备好，可以开始第一份申请</h2>
        <p>从岗位雷达选择已验证岗位；手动申请与 Browser Agent 都会写入同一投递中心。</p>
      </article>
    );
  }

  return (
    <article className="empty-panel">
      <h2>工作台已接入真实求职数据</h2>
      <p>
        当前共有 {summary.applications_total} 条投递记录；岗位发现、入口验证、Browser Agent 与投递中心已形成同一条工作流。
      </p>
    </article>
  );
}
