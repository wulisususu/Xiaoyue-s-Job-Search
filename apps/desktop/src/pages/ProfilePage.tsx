import { useEffect, useMemo, useState } from 'react';

import {
  acceptProfileDraft,
  getPendingProfileDrafts,
  getProfileDefinitions,
  getProfileFields,
  rejectProfileDraft,
  saveProfileField,
  type ProfileDefinition,
  type ProfileDraft,
  type ProfileField,
} from '../api/profileClient';
import '../styles/profile.css';

function valueToEditorText(value: unknown): string {
  if (Array.isArray(value)) return value.join('\n');
  if (value === null || value === undefined) return '';
  return String(value);
}

function parseEditorValue(definition: ProfileDefinition, raw: string): unknown {
  if (definition.multiple) {
    return raw
      .split(/[\n,，]/)
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return raw;
}

function displayValue(value: unknown): string {
  if (Array.isArray(value)) return value.join('、');
  if (value === null || value === undefined) return '';
  return String(value);
}

function sourceLabel(field: ProfileField | undefined): string {
  if (!field) return '待填写';
  if (field.source_type === 'resume') return '简历确认';
  if (field.source_type === 'manual') return '手动确认';
  return '已确认';
}

function upsertField(items: ProfileField[], incoming: ProfileField): ProfileField[] {
  return [...items.filter((item) => item.field_key !== incoming.field_key), incoming];
}

export function ProfilePage() {
  const [definitions, setDefinitions] = useState<ProfileDefinition[]>([]);
  const [fields, setFields] = useState<ProfileField[]>([]);
  const [drafts, setDrafts] = useState<ProfileDraft[]>([]);
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [savingField, setSavingField] = useState<string | null>(null);
  const [reviewingDraft, setReviewingDraft] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([getProfileDefinitions(), getProfileFields(), getPendingProfileDrafts()])
      .then(([nextDefinitions, nextFields, nextDrafts]) => {
        if (!active) return;
        setDefinitions(nextDefinitions);
        setFields(nextFields);
        setDrafts(nextDrafts);
        const nextEditValues: Record<string, string> = {};
        for (const definition of nextDefinitions) {
          const field = nextFields.find((item) => item.field_key === definition.field_key);
          nextEditValues[definition.field_key] = valueToEditorText(field?.value);
        }
        setEditValues(nextEditValues);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : '个人资料加载失败');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const fieldsByKey = useMemo(
    () => new Map(fields.map((field) => [field.field_key, field])),
    [fields],
  );

  const categories = useMemo(() => {
    const grouped = new Map<string, ProfileDefinition[]>();
    for (const definition of definitions) {
      const group = grouped.get(definition.category) ?? [];
      group.push(definition);
      grouped.set(definition.category, group);
    }
    return [...grouped.entries()];
  }, [definitions]);

  async function handleSave(definition: ProfileDefinition) {
    setSavingField(definition.field_key);
    setError(null);
    setMessage(null);
    try {
      const value = parseEditorValue(definition, editValues[definition.field_key] ?? '');
      const saved = await saveProfileField(definition.field_key, value);
      setFields((items) => upsertField(items, saved));
      setEditValues((items) => ({ ...items, [definition.field_key]: valueToEditorText(saved.value) }));
      setMessage(`${definition.label}已保存并写入 Profile SSOT。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${definition.label}保存失败`);
    } finally {
      setSavingField(null);
    }
  }

  async function handleAccept(draft: ProfileDraft) {
    setReviewingDraft(draft.id);
    setError(null);
    setMessage(null);
    try {
      const accepted = await acceptProfileDraft(draft.id);
      setFields((items) => upsertField(items, accepted));
      setEditValues((items) => ({ ...items, [accepted.field_key]: valueToEditorText(accepted.value) }));
      setDrafts((items) => items.filter((item) => item.id !== draft.id));
      setMessage(`${draft.label}候选已人工确认并写入 Profile SSOT。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${draft.label}候选确认失败`);
    } finally {
      setReviewingDraft(null);
    }
  }

  async function handleReject(draft: ProfileDraft) {
    setReviewingDraft(draft.id);
    setError(null);
    setMessage(null);
    try {
      await rejectProfileDraft(draft.id);
      setDrafts((items) => items.filter((item) => item.id !== draft.id));
      setMessage(`${draft.label}候选已拒绝，正式资料未发生变化。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${draft.label}候选拒绝失败`);
    } finally {
      setReviewingDraft(null);
    }
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Profile SSOT</p>
          <h1>我的资料</h1>
          <p>这是网申自动填写时唯一可信的结构化个人信息源；简历解析结果必须人工审核后才能进入这里。</p>
        </div>
        <div className="profile-header-status">
          <strong>{fields.length} / {definitions.length}</strong>
          <span>{fields.length === 0 ? '尚未确认' : '已确认字段'}</span>
        </div>
      </header>

      {message && <p className="resume-message success">{message}</p>}
      {error && <p className="resume-message error">{error}</p>}

      {loading ? (
        <article className="empty-panel">
          <h2>正在读取个人资料</h2>
          <p>同时加载字段定义、已确认 Profile 和待审核的简历候选。</p>
        </article>
      ) : (
        <>
          <section className="profile-review-panel" aria-labelledby="profile-draft-title">
            <div className="profile-section-heading">
              <div>
                <h2 id="profile-draft-title">待审核候选</h2>
                <p>候选值来自简历解析。点击“接受”前，它们不会进入正式 Profile，也不会参与自动填表。</p>
              </div>
              <span className="soft-badge warning">{drafts.length} 项</span>
            </div>

            {drafts.length === 0 ? (
              <p className="profile-empty-note">当前没有待审核的简历候选。</p>
            ) : (
              <div className="profile-draft-list">
                {drafts.map((draft) => (
                  <article className="profile-draft-card" key={draft.id}>
                    <div>
                      <div className="badge-row">
                        <span className="soft-badge">{draft.category}</span>
                        <span className="soft-badge verified">置信度 {Math.round((draft.confidence ?? 0) * 100)}%</span>
                      </div>
                      <h3>{draft.label}</h3>
                      <p className="profile-draft-value">{displayValue(draft.value)}</p>
                      <p className="profile-draft-source">{draft.resume_filename} · V{draft.resume_version_number}</p>
                    </div>
                    <div className="profile-draft-actions">
                      <button
                        className="primary-button"
                        type="button"
                        aria-label={`接受 ${draft.label}`}
                        disabled={reviewingDraft === draft.id}
                        onClick={() => handleAccept(draft)}
                      >
                        接受
                      </button>
                      <button
                        className="secondary-button"
                        type="button"
                        aria-label={`拒绝 ${draft.label}`}
                        disabled={reviewingDraft === draft.id}
                        onClick={() => handleReject(draft)}
                      >
                        拒绝
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </section>

          <div className="profile-category-list">
            {categories.map(([category, categoryDefinitions]) => (
              <section className="profile-category" key={category}>
                <div className="profile-section-heading">
                  <div>
                    <h2>{category}</h2>
                    <p>手动保存会立即成为已确认 SSOT，并记录 revision。</p>
                  </div>
                </div>
                <div className="profile-field-list">
                  {categoryDefinitions.map((definition) => {
                    const field = fieldsByKey.get(definition.field_key);
                    const isLongText = definition.multiple || definition.field_key.endsWith('.summary');
                    return (
                      <div
                        className="profile-field-row"
                        data-testid={`profile-field-${definition.field_key}`}
                        key={definition.field_key}
                      >
                        <label className="profile-field-control">
                          <span>{definition.label}</span>
                          {isLongText ? (
                            <textarea
                              aria-label={definition.label}
                              rows={definition.multiple ? 3 : 4}
                              placeholder={definition.multiple ? '每行填写一项' : `填写${definition.label}`}
                              value={editValues[definition.field_key] ?? ''}
                              onChange={(event) => setEditValues((items) => ({ ...items, [definition.field_key]: event.target.value }))}
                            />
                          ) : (
                            <input
                              aria-label={definition.label}
                              type="text"
                              placeholder={`填写${definition.label}`}
                              value={editValues[definition.field_key] ?? ''}
                              onChange={(event) => setEditValues((items) => ({ ...items, [definition.field_key]: event.target.value }))}
                            />
                          )}
                        </label>
                        <div className="profile-field-meta">
                          <span className={`soft-badge${field ? ' verified' : ''}`}>{sourceLabel(field)}</span>
                          {field?.updated_at && <span>更新于 {new Date(field.updated_at).toLocaleString('zh-CN')}</span>}
                        </div>
                        <button
                          className="secondary-button"
                          type="button"
                          aria-label={`保存 ${definition.label}`}
                          disabled={savingField === definition.field_key}
                          onClick={() => handleSave(definition)}
                        >
                          {savingField === definition.field_key ? '保存中…' : '保存'}
                        </button>
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
