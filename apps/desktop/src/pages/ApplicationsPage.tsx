import { useCallback, useEffect, useMemo, useState } from 'react';

import { ApplicationRecord, getApplications, updateApplicationStatus } from '../api/applicationsClient';
import {
  closeBrowserAgentSession,
  fillBrowserAgentPlan,
  getBrowserAgentSessions,
  getBrowserFillPlan,
  getBrowserSemanticPlan,
  startBrowserAgentSession,
  type BrowserAgentSession,
  type BrowserFillPlan,
} from '../api/browserAgentClient';

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
  const [sessions, setSessions] = useState<BrowserAgentSession[]>([]);
  const [plans, setPlans] = useState<Record<number, BrowserFillPlan>>({});
  const [approved, setApproved] = useState<Record<number, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [agentBusyId, setAgentBusyId] = useState<number | null>(null);

  const sessionsByApplication = useMemo(
    () => new Map(sessions.map((session) => [session.application_id, session])),
    [sessions],
  );

  const refresh = useCallback(() => {
    setLoading(true);
    setError('');
    Promise.all([getApplications(), getBrowserAgentSessions()])
      .then(([applicationRows, agentSessions]) => {
        setApplications(applicationRows);
        setSessions(agentSessions);
      })
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

  async function ensureAgent(applicationId: number): Promise<BrowserAgentSession> {
    const existing = sessionsByApplication.get(applicationId);
    if (existing) return existing;
    const created = await startBrowserAgentSession(applicationId);
    setSessions((current) => [...current.filter((item) => item.application_id !== applicationId), created]);
    return created;
  }

  async function scanApplication(applicationId: number) {
    setAgentBusyId(applicationId);
    setError('');
    setMessage('');
    try {
      const session = await ensureAgent(applicationId);
      const plan = await getBrowserFillPlan(session.id);
      setPlans((current) => ({ ...current, [applicationId]: plan }));
      setApproved((current) => ({
        ...current,
        [applicationId]: plan.items.filter((item) => !item.requires_confirmation).map((item) => item.field_id),
      }));
      setMessage(`已扫描当前页面：可建议填写 ${plan.items.length} 项，未匹配 ${plan.unmatched.length} 项。`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '表单扫描失败');
    } finally {
      setAgentBusyId(null);
    }
  }

  async function augmentWithAI(applicationId: number) {
    const plan = plans[applicationId];
    const session = sessionsByApplication.get(applicationId);
    if (!plan || !session || plan.unmatched.length === 0) return;
    setAgentBusyId(applicationId);
    setError('');
    setMessage('');
    try {
      const updated = await getBrowserSemanticPlan(session.id, plan.token);
      setPlans((current) => ({ ...current, [applicationId]: updated }));
      setApproved((current) => {
        const previous = new Set(current[applicationId] ?? []);
        const validIds = new Set(updated.items.map((item) => item.field_id));
        return {
          ...current,
          [applicationId]: Array.from(previous).filter((fieldId) => validIds.has(fieldId)),
        };
      });
      const added = Math.max(0, updated.items.length - plan.items.length);
      setMessage(
        `AI 补全完成：新增 ${added} 项语义建议。AI 建议默认不勾选，请逐项确认后再填写。`,
      );
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : 'AI 语义补全失败');
    } finally {
      setAgentBusyId(null);
    }
  }

  function toggleApproved(applicationId: number, fieldId: string) {
    setApproved((current) => {
      const selected = new Set(current[applicationId] ?? []);
      if (selected.has(fieldId)) selected.delete(fieldId);
      else selected.add(fieldId);
      return { ...current, [applicationId]: Array.from(selected) };
    });
  }

  async function fillApproved(applicationId: number) {
    const plan = plans[applicationId];
    const session = sessionsByApplication.get(applicationId);
    if (!plan || !session) return;
    setAgentBusyId(applicationId);
    setError('');
    setMessage('');
    try {
      const fieldIds = approved[applicationId] ?? [];
      const result = await fillBrowserAgentPlan(session.id, plan.token, fieldIds);
      setMessage(`已填写 ${result.filled_count} 项，跳过 ${result.skipped_count} 项。请在浏览器中逐项检查，提交仍需你本人确认。`);
      const rows = await getApplications();
      setApplications(rows);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '表单填写失败');
    } finally {
      setAgentBusyId(null);
    }
  }

  async function endAgent(applicationId: number) {
    const session = sessionsByApplication.get(applicationId);
    if (!session) return;
    setAgentBusyId(applicationId);
    try {
      await closeBrowserAgentSession(session.id);
      setSessions((current) => current.filter((item) => item.id !== session.id));
      setPlans((current) => {
        const next = { ...current };
        delete next[applicationId];
        return next;
      });
      setMessage('智能填写会话已结束。');
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '结束智能填写失败');
    } finally {
      setAgentBusyId(null);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">CRM</p>
          <h1>投递中心</h1>
          <p>手动投递与 Browser Agent 共用同一 Application SSOT；智能填写只读取已确认 Profile，最终提交始终由你本人完成。</p>
        </div>
      </header>

      {message && <p className="resume-message success" role="status">{message}</p>}
      {loading && <article className="empty-panel"><p>正在读取投递记录…</p></article>}
      {error && <article className="empty-panel"><h2>投递记录加载失败</h2><p>{error}</p></article>}
      {!loading && !error && applications.length === 0 && (
        <article className="empty-panel">
          <h2>暂无投递记录</h2>
          <p>在岗位雷达中验证入口后点击“智能填写”或“开始申请”，这里会出现第一条记录。</p>
        </article>
      )}

      {!loading && !error && applications.length > 0 && (
        <div className="job-list">
          {applications.map((application) => {
            const agentSession = sessionsByApplication.get(application.id);
            const plan = plans[application.id];
            const selected = new Set(approved[application.id] ?? []);
            const isAgent = application.channel === 'browser_agent';
            return (
              <article className="job-card application-card" key={application.id}>
                <div className="job-card-main">
                  <div className="badge-row">
                    <span className="soft-badge verified">{statusLabel[application.status] ?? application.status}</span>
                    <span className={`soft-badge ${isAgent ? 'ats-badge' : ''}`}>{isAgent ? '智能填写' : '手动投递'}</span>
                    {agentSession && <span className="soft-badge verified">受控浏览器运行中</span>}
                  </div>
                  <h2>{application.company_name}</h2>
                  <h3>{application.job_title}</h3>
                  <p className="job-verification">开始时间：{formatTime(application.opened_at)} · 最近更新：{formatTime(application.updated_at)}</p>
                  {application.opened_url && <p className="job-source">入口：{application.opened_url}</p>}

                  {isAgent && (
                    <section className="agent-panel" aria-label="智能填写">
                      <div className="agent-panel-header">
                        <div>
                          <strong>Browser Agent</strong>
                          <p>{agentSession ? '在受控 Edge 中登录并进入目标表单后，扫描当前页面。' : '受控浏览器未运行，可重新启动。'}</p>
                        </div>
                        <div className="agent-actions">
                          <button
                            className="secondary-button"
                            disabled={agentBusyId === application.id}
                            onClick={() => scanApplication(application.id)}
                            type="button"
                          >
                            {agentBusyId === application.id ? '处理中…' : agentSession ? '扫描表单' : '启动并扫描'}
                          </button>
                          {agentSession && (
                            <button className="secondary-button" disabled={agentBusyId === application.id} onClick={() => endAgent(application.id)} type="button">
                              结束会话
                            </button>
                          )}
                        </div>
                      </div>

                      {plan && (
                        <div className="agent-plan">
                          <div className="agent-safety-note">
                            只会填写你勾选的字段；密码、附件、提交控件会被阻断。Browser Agent <strong>不会点击提交按钮</strong>。
                          </div>
                          <div className="agent-plan-list">
                            {plan.items.map((item) => (
                              <label className={`agent-plan-row ${item.requires_confirmation ? 'needs-review' : ''}`} key={item.field_id}>
                                <input
                                  aria-label={`${item.label} ${item.source_path}`}
                                  type="checkbox"
                                  checked={selected.has(item.field_id)}
                                  onChange={() => toggleApproved(application.id, item.field_id)}
                                />
                                <span className="agent-plan-copy">
                                  <strong>{item.label}</strong>
                                  <small><code>{item.source_path}</code> · 置信度 {Math.round(item.confidence * 100)}%</small>
                                </span>
                                <span className="agent-value">{formatAgentValue(item.value)}</span>
                                {item.requires_confirmation && <span className="soft-badge warning">需确认</span>}
                              </label>
                            ))}
                          </div>

                          {plan.unmatched.length > 0 && (
                            <>
                              <p className="agent-unmatched">未自动匹配：{plan.unmatched.map((item) => item.label || item.field_id).join('、')}</p>
                              <button
                                className="secondary-button"
                                disabled={agentBusyId === application.id}
                                onClick={() => augmentWithAI(application.id)}
                                type="button"
                              >
                                AI 补全未匹配
                              </button>
                            </>
                          )}
                          {plan.blocked.length > 0 && (
                            <p className="agent-blocked">安全阻断：{plan.blocked.map((item) => item.label || item.field_id).join('、')}</p>
                          )}

                          <button
                            className="primary-button"
                            disabled={agentBusyId === application.id || selected.size === 0}
                            onClick={() => fillApproved(application.id)}
                            type="button"
                          >
                            填写已确认项
                          </button>
                        </div>
                      )}
                    </section>
                  )}
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
            );
          })}
        </div>
      )}
    </section>
  );
}

function formatAgentValue(value: unknown): string {
  if (Array.isArray(value)) return value.join('；');
  if (value === null || value === undefined) return '';
  return String(value);
}

function formatTime(value: string | null) {
  if (!value) return '未知';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false });
}
