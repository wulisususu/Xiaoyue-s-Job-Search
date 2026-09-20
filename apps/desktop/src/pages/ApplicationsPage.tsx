import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  ApplicationRecord,
  getApplicationEvents,
  getApplications,
  updateApplicationStatus,
  type ApplicationEventRecord,
} from '../api/applicationsClient';
import { getResumes, type ResumeVersion } from '../api/resumesClient';
import {
  closeBrowserAgentSession,
  confirmBrowserAgentVerification,
  fillBrowserAgentPlan,
  getBrowserAgentSessions,
  getBrowserFillPlan,
  getBrowserSemanticPlan,
  startBrowserAgentSession,
  uploadBrowserAgentResume,
  type BrowserAgentSession,
  type BrowserAttachmentPlanItem,
  type BrowserFillFieldResult,
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

export function ApplicationsPage() {
  const [applications, setApplications] = useState<ApplicationRecord[]>([]);
  const [sessions, setSessions] = useState<BrowserAgentSession[]>([]);
  const [plans, setPlans] = useState<Record<number, BrowserFillPlan>>({});
  const [approved, setApproved] = useState<Record<number, string[]>>({});
  const [fillResults, setFillResults] = useState<Record<number, BrowserFillFieldResult[]>>({});
  const [resumes, setResumes] = useState<ResumeVersion[]>([]);
  const [resumeSelections, setResumeSelections] = useState<Record<string, string>>({});
  const [uploadedResumes, setUploadedResumes] = useState<Record<string, string>>({});
  const [timelineEvents, setTimelineEvents] = useState<Record<number, ApplicationEventRecord[]>>({});
  const [expandedTimelineId, setExpandedTimelineId] = useState<number | null>(null);
  const [timelineLoadingId, setTimelineLoadingId] = useState<number | null>(null);
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
    Promise.all([getApplications(), getBrowserAgentSessions(), getResumes()])
      .then(([applicationRows, agentSessions, resumeRows]) => {
        setApplications(applicationRows);
        setSessions(agentSessions);
        setResumes(resumeRows);
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
      if (expandedTimelineId === id) {
        const events = await getApplicationEvents(id);
        setTimelineEvents((current) => ({ ...current, [id]: events }));
      }
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '状态更新失败');
    } finally {
      setUpdatingId(null);
    }
  }

  async function toggleTimeline(applicationId: number) {
    if (expandedTimelineId === applicationId) {
      setExpandedTimelineId(null);
      return;
    }
    setExpandedTimelineId(applicationId);
    if (timelineEvents[applicationId]) return;

    setTimelineLoadingId(applicationId);
    setError('');
    try {
      const events = await getApplicationEvents(applicationId);
      setTimelineEvents((current) => ({ ...current, [applicationId]: events }));
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '投递时间线加载失败');
    } finally {
      setTimelineLoadingId(null);
    }
  }

  async function ensureAgent(application: ApplicationRecord): Promise<BrowserAgentSession> {
    const existing = sessionsByApplication.get(application.id);
    if (existing) return existing;
    const mode = application.job_status === 'VERIFIED_OPEN' ? 'fill' : 'verify';
    const created = await startBrowserAgentSession(application.id, mode);
    setSessions((current) => [...current.filter((item) => item.application_id !== application.id), created]);
    return created;
  }

  function storePlan(applicationId: number, plan: BrowserFillPlan) {
    setPlans((current) => ({ ...current, [applicationId]: plan }));
    setFillResults((current) => ({ ...current, [applicationId]: [] }));
    setApproved((current) => ({
      ...current,
      [applicationId]: plan.items.filter((item) => !item.requires_confirmation).map((item) => item.field_id),
    }));
  }

  async function scanApplication(application: ApplicationRecord) {
    setAgentBusyId(application.id);
    setError('');
    setMessage('');
    try {
      let session = await ensureAgent(application);
      if (session.mode === 'verify') {
        const wasAlreadyRunning = sessionsByApplication.has(application.id);
        if (!wasAlreadyRunning) {
          setMessage('浏览器复核已启动。请在受控 Edge 中完成登录/验证码并进入实际网申表单，然后再次点击“确认网申表单”。');
          return;
        }

        const verification = await confirmBrowserAgentVerification(session.id);
        session = { ...session, mode: 'fill', url: verification.page_url };
        setSessions((current) => [
          ...current.filter((item) => item.application_id !== application.id),
          session,
        ]);
        const rows = await getApplications();
        setApplications(rows);

        const plan = await getBrowserFillPlan(session.id);
        storePlan(application.id, plan);
        setMessage(
          `浏览器复核通过，已转入安全填写模式。可建议填写 ${plan.items.length} 项，未匹配 ${plan.unmatched.length} 项。`,
        );
        return;
      }

      const plan = await getBrowserFillPlan(session.id);
      storePlan(application.id, plan);
      setMessage(`已扫描当前页面：可建议填写 ${plan.items.length} 项，未匹配 ${plan.unmatched.length} 项。`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '表单扫描/复核失败');
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
      setFillResults((current) => ({ ...current, [applicationId]: result.results }));
      setMessage(
        `写入尝试 ${result.filled_count} 项；回读验证成功 ${result.verified_count} 项，失败 ${result.failed_count} 项，需要检查 ${result.uncertain_count} 项，跳过 ${result.skipped_count} 项。最终提交仍需你本人确认。`,
      );
      const rows = await getApplications();
      setApplications(rows);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '表单填写失败');
    } finally {
      setAgentBusyId(null);
    }
  }

  async function uploadResumeAttachment(
    applicationId: number,
    attachment: BrowserAttachmentPlanItem,
  ) {
    const plan = plans[applicationId];
    const session = sessionsByApplication.get(applicationId);
    const key = attachmentSelectionKey(applicationId, attachment.field_id);
    const resumeVersionId = resumeSelections[key];
    if (!plan || !session || !resumeVersionId) return;

    setAgentBusyId(applicationId);
    setError('');
    setMessage('');
    try {
      const result = await uploadBrowserAgentResume(
        session.id,
        plan.token,
        attachment.field_id,
        resumeVersionId,
      );
      setUploadedResumes((current) => ({ ...current, [key]: result.filename }));
      setMessage(
        `已将简历版本上传到“${attachment.label}”：${result.filename}。页面仍未提交，请继续人工检查。`,
      );
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : '简历上传失败');
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
      setFillResults((current) => {
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
            const fieldResultsById = new Map(
              (fillResults[application.id] ?? []).map((result) => [result.field_id, result]),
            );
            const isAgent = application.channel === 'browser_agent';
            const statusChoices = [application.status, ...application.allowed_next_statuses];
            const events = timelineEvents[application.id] ?? [];
            const timelineExpanded = expandedTimelineId === application.id;
            return (
              <article className="job-card application-card" key={application.id}>
                <div className="job-card-main">
                  <div className="badge-row">
                    <span className="soft-badge verified">{statusLabel[application.status] ?? application.status}</span>
                    <span className={`soft-badge ${isAgent ? 'ats-badge' : ''}`}>{isAgent ? '智能填写' : '手动投递'}</span>
                    {agentSession && (
                      <span className={`soft-badge ${agentSession.mode === 'verify' ? 'warning' : 'verified'}`}>
                        {agentSession.mode === 'verify' ? '浏览器复核中' : '安全填写模式'}
                      </span>
                    )}
                  </div>
                  <h2>{application.company_name}</h2>
                  <h3>{application.job_title}</h3>
                  <p className="job-verification">开始时间：{formatTime(application.opened_at)} · 最近更新：{formatTime(application.updated_at)}</p>
                  {application.opened_url && <p className="job-source">入口：{application.opened_url}</p>}
                  {application.resume_version_id && (
                    <p className="job-source">简历版本：<code>{application.resume_version_id}</code></p>
                  )}

                  <div className="application-history-actions">
                    <button
                      className="secondary-button"
                      type="button"
                      disabled={timelineLoadingId === application.id}
                      onClick={() => toggleTimeline(application.id)}
                    >
                      {timelineLoadingId === application.id
                        ? '加载中…'
                        : timelineExpanded
                          ? '收起时间线'
                          : '查看时间线'}
                    </button>
                  </div>

                  {timelineExpanded && (
                    <section className="application-timeline" aria-label="投递时间线">
                      {events.length === 0 && timelineLoadingId !== application.id && (
                        <p className="application-timeline-empty">暂无时间线事件。</p>
                      )}
                      {events.map((event) => (
                        <article className="application-event" key={event.id}>
                          <span className="application-event-dot" aria-hidden="true" />
                          <div>
                            <strong>{applicationEventLabel(event)}</strong>
                            <small>{formatTime(event.created_at)}</small>
                            {event.note && <p>{event.note}</p>}
                          </div>
                        </article>
                      ))}
                    </section>
                  )}

                  {isAgent && (
                    <section className="agent-panel" aria-label="智能填写">
                      <div className="agent-panel-header">
                        <div>
                          <strong>Browser Agent</strong>
                          <p>
                            {agentSession?.mode === 'verify'
                              ? '复核模式只允许读取页面，不会生成填写计划。完成登录/验证码并进入实际网申表单后再确认。'
                              : agentSession
                                ? '已进入填写模式；扫描当前页后只填写你明确勾选的字段。'
                                : application.job_status === 'VERIFIED_OPEN'
                                  ? '受控浏览器未运行，可启动后扫描表单。'
                                  : '该岗位尚未静态验证通过，将先以只读浏览器复核模式启动。'}
                          </p>
                        </div>
                        <div className="agent-actions">
                          <button
                            className="secondary-button"
                            disabled={agentBusyId === application.id}
                            onClick={() => scanApplication(application)}
                            type="button"
                          >
                            {agentBusyId === application.id
                              ? '处理中…'
                              : agentSession?.mode === 'verify'
                                ? '确认网申表单'
                                : agentSession
                                  ? '扫描表单'
                                  : application.job_status === 'VERIFIED_OPEN'
                                    ? '启动并扫描'
                                    : '启动浏览器复核'}
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
                            <strong>{plan.adapter_display_name}</strong>
                            {' · '}
                            {adapterImplementationLabel(plan.adapter_implementation)}
                            {' · '}
                            只会填写你勾选的字段；密码、非受控附件、提交控件会被阻断。Browser Agent <strong>不会点击提交按钮</strong>。
                            {plan.adapter_limitations.length > 0 && (
                              <small className="agent-adapter-limitations">
                                当前仍需人工：{plan.adapter_limitations.map(adapterLimitationLabel).join('、')}
                              </small>
                            )}
                          </div>
                          <div className="agent-plan-list">
                            {plan.items.map((item) => {
                              const fieldResult = fieldResultsById.get(item.field_id);
                              return (
                                <label className={`agent-plan-row ${item.requires_confirmation ? 'needs-review' : ''}`} key={item.field_id}>
                                  <input
                                    aria-label={`${item.label} ${item.source_path}`}
                                    type="checkbox"
                                    checked={selected.has(item.field_id)}
                                    onChange={() => toggleApproved(application.id, item.field_id)}
                                  />
                                  <span className="agent-plan-copy">
                                    <strong>{item.label}</strong>
                                    <small>
                                      <code>{item.source_path}</code> · 置信度 {Math.round(item.confidence * 100)}%
                                      {fieldResult && <> · 回读：{formatAgentValue(fieldResult.observed)}</>}
                                    </small>
                                  </span>
                                  <span className="agent-value">{formatAgentValue(item.value)}</span>
                                  {fieldResult ? (
                                    <span className={`soft-badge ${fillResultBadgeClass(fieldResult.status)}`}>
                                      {fillResultLabel(fieldResult.status)}
                                    </span>
                                  ) : item.requires_confirmation ? (
                                    <span className="soft-badge warning">需确认</span>
                                  ) : null}
                                </label>
                              );
                            })}
                          </div>

                          {plan.attachments.length > 0 && (
                            <div className="agent-attachment-list">
                              {plan.attachments.map((attachment) => {
                                const key = attachmentSelectionKey(application.id, attachment.field_id);
                                const selectedResume = resumeSelections[key] ?? '';
                                const uploadedFilename = uploadedResumes[key];
                                return (
                                  <div className="agent-attachment-row" key={attachment.field_id}>
                                    <div className="agent-plan-copy">
                                      <strong>{attachment.label}</strong>
                                      <small>
                                        {attachment.required ? '必填' : '选填'} · 仅接受 Resume Vault 中已验证的 PDF/DOCX
                                      </small>
                                    </div>
                                    <select
                                      aria-label={`选择${attachment.label}版本`}
                                      value={selectedResume}
                                      onChange={(event) => {
                                        const value = event.target.value;
                                        setResumeSelections((current) => ({ ...current, [key]: value }));
                                        setUploadedResumes((current) => {
                                          const next = { ...current };
                                          delete next[key];
                                          return next;
                                        });
                                      }}
                                    >
                                      <option value="">请选择简历版本</option>
                                      {resumes.map((resume) => (
                                        <option key={resume.id} value={resume.id}>
                                          v{resume.version_number} · {resume.original_filename}
                                        </option>
                                      ))}
                                    </select>
                                    <button
                                      className="secondary-button"
                                      type="button"
                                      disabled={!selectedResume || agentBusyId === application.id}
                                      onClick={() => uploadResumeAttachment(application.id, attachment)}
                                    >
                                      上传所选简历
                                    </button>
                                    {uploadedFilename && (
                                      <span className="soft-badge verified">已回读：{uploadedFilename}</span>
                                    )}
                                  </div>
                                );
                              })}
                              {resumes.length === 0 && (
                                <p className="agent-unmatched">Resume Vault 暂无可选版本，请先导入简历。</p>
                              )}
                            </div>
                          )}

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
                    {statusChoices.map((option) => (
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


function fillResultLabel(status: BrowserFillFieldResult['status']): string {
  if (status === 'VERIFIED') return '回读成功';
  if (status === 'FAILED') return '填写失败';
  if (status === 'UNCERTAIN') return '需检查';
  return '已跳过';
}

function fillResultBadgeClass(status: BrowserFillFieldResult['status']): string {
  return status === 'VERIFIED' ? 'verified' : 'warning';
}


function adapterLimitationLabel(value: string): string {
  const labels: Record<string, string> = {
    file_upload: '附件上传',
    additional_attachments: '其他附件上传',
    cascading_select: '级联选择',
    repeatable_sections: '重复经历区块',
    repeatable_sections_without_native_paths: '无原生路径的重复经历区块',
    practice_experience_disambiguation: '实习/工作经历归类',
    moka_custom_fields: 'Moka 自定义字段',
    iframe_forms: 'iframe 表单',
    multi_step_navigation: '多步骤自动导航',
    auto_submit: '自动提交',
  };
  return labels[value] ?? value;
}


function adapterImplementationLabel(value: string): string {
  if (value === 'generic_dom') return '通用 DOM 兼容层';
  if (value === 'moka_dom_v1') return 'Moka 专项 DOM v1';
  return value;
}


function attachmentSelectionKey(applicationId: number, fieldId: string): string {
  return `${applicationId}:${fieldId}`;
}


function applicationEventLabel(event: ApplicationEventRecord): string {
  if (event.event_type === 'CREATED') return '创建投递记录';
  if (event.event_type === 'STATUS_CHANGED') {
    const from = event.from_status ? statusLabel[event.from_status] ?? event.from_status : '未知';
    const to = statusLabel[event.to_status] ?? event.to_status;
    return `${from} → ${to}`;
  }
  return event.event_type;
}
