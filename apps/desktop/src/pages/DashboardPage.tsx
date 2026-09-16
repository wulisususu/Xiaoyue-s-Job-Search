import { useEffect, useState } from 'react';
import { getCoreHealth } from '../api/coreClient';

const metrics = [['今日新增岗位','0'],['可申请岗位','0'],['已收藏','0'],['填写中','0'],['已投递','0'],['笔试','0'],['面试','0'],['Offer','0']] as const;

export function DashboardPage() {
  const [coreConnected, setCoreConnected] = useState<boolean | null>(null);
  useEffect(() => {
    let mounted = true;
    getCoreHealth().then(() => mounted && setCoreConnected(true)).catch(() => mounted && setCoreConnected(false));
    return () => { mounted = false; };
  }, []);
  return <section className="page"><header className="page-header"><div><p className="eyebrow">Dashboard</p><h1>首页</h1><p>你的央国企求职进度与本地工作台状态。</p></div><span className={`status-pill ${coreConnected ? 'online' : ''}`}>本地核心：{coreConnected === null ? '检测中' : coreConnected ? '已连接' : '未连接'}</span></header><div className="metric-grid">{metrics.map(([label,value]) => <article className="metric-card" key={label}><span>{label}</span><strong>{value}</strong></article>)}</div><article className="empty-panel"><h2>从建立个人资料开始</h2><p>当前还没有岗位和投递数据。后续里程碑会接入 WorkFind、Xiaozhao Radar 和 Browser Agent。</p></article></section>;
}
