import { useEffect, useMemo, useState } from 'react';

import {
  acceptProfileCollectionDraft,
  acceptProfileDraft,
  createProfileCollectionItem,
  deleteProfileCollectionItem,
  getPendingProfileCollectionDrafts,
  getPendingProfileDrafts,
  getProfileCollection,
  getProfileCollectionDefinitions,
  getProfileDefinitions,
  getProfileFields,
  rejectProfileCollectionDraft,
  rejectProfileDraft,
  reorderProfileCollectionItems,
  saveProfileField,
  updateProfileCollectionItem,
  type ProfileCollectionDefinition,
  type ProfileCollectionDraft,
  type ProfileCollectionFieldDefinition,
  type ProfileCollectionItem,
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

function collectionSourceLabel(item: ProfileCollectionItem): string {
  if (item.source_type === 'resume') return '简历确认';
  if (item.source_type === 'manual') return '手动确认';
  if (item.source_type === 'ai') return 'AI 候选确认';
  return '已确认';
}

function upsertField(items: ProfileField[], incoming: ProfileField): ProfileField[] {
  return [...items.filter((item) => item.field_key !== incoming.field_key), incoming];
}

function collectionItemEditor(
  definition: ProfileCollectionDefinition,
  item: ProfileCollectionItem,
): Record<string, string> {
  const values: Record<string, string> = {};
  for (const field of definition.fields) {
    values[field.key] = valueToEditorText(item.payload[field.key]);
  }
  return values;
}

function collectionEditorPayload(
  definition: ProfileCollectionDefinition,
  values: Record<string, string>,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {};
  for (const field of definition.fields) {
    const raw = values[field.key] ?? '';
    if (field.multiple) {
      const entries = raw
        .split(/[\n,，]/)
        .map((entry) => entry.trim())
        .filter(Boolean);
      if (entries.length > 0) payload[field.key] = entries;
      continue;
    }
    const normalized = raw.trim();
    if (normalized) payload[field.key] = normalized;
  }
  return payload;
}

function CollectionInput({
  field,
  values,
  setValue,
  ariaPrefix,
}: {
  field: ProfileCollectionFieldDefinition;
  values: Record<string, string>;
  setValue: (key: string, value: string) => void;
  ariaPrefix: string;
}) {
  const isLongText = field.multiple || field.key === 'description';
  return (
    <label className="profile-collection-control">
      <span>
        {field.label}
        {field.required && <em>必填</em>}
      </span>
      {isLongText ? (
        <textarea
          aria-label={`${ariaPrefix} ${field.label}`}
          rows={field.multiple ? 3 : 4}
          placeholder={field.multiple ? '每行填写一项' : `填写${field.label}`}
          value={values[field.key] ?? ''}
          onChange={(event) => setValue(field.key, event.target.value)}
        />
      ) : (
        <input
          aria-label={`${ariaPrefix} ${field.label}`}
          type="text"
          placeholder={`填写${field.label}`}
          value={values[field.key] ?? ''}
          onChange={(event) => setValue(field.key, event.target.value)}
        />
      )}
    </label>
  );
}

function ProfileCollectionSection({
  definition,
  refreshVersion,
  onMessage,
  onError,
}: {
  definition: ProfileCollectionDefinition;
  refreshVersion: number;
  onMessage: (message: string) => void;
  onError: (message: string) => void;
}) {
  const [items, setItems] = useState<ProfileCollectionItem[]>([]);
  const [editors, setEditors] = useState<Record<number, Record<string, string>>>({});
  const [adding, setAdding] = useState(false);
  const [newEditor, setNewEditor] = useState<Record<string, string>>({});
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  function syncItems(nextItems: ProfileCollectionItem[]) {
    const ordered = [...nextItems].sort(
      (left, right) => left.position - right.position || left.id - right.id,
    );
    setItems(ordered);
    const nextEditors: Record<number, Record<string, string>> = {};
    for (const item of ordered) {
      nextEditors[item.id] = collectionItemEditor(definition, item);
    }
    setEditors(nextEditors);
  }

  useEffect(() => {
    let active = true;
    setLoading(true);
    getProfileCollection(definition.kind)
      .then((nextItems) => {
        if (active) syncItems(nextItems);
      })
      .catch((reason: unknown) => {
        if (active) onError(reason instanceof Error ? reason.message : `${definition.label}加载失败`);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [definition.kind, refreshVersion]);

  function updateEditor(itemId: number, key: string, value: string) {
    setEditors((current) => ({
      ...current,
      [itemId]: { ...(current[itemId] ?? {}), [key]: value },
    }));
  }

  async function handleSave(item: ProfileCollectionItem, index: number) {
    const action = `save-${item.id}`;
    setBusyAction(action);
    onError('');
    try {
      const payload = collectionEditorPayload(definition, editors[item.id] ?? {});
      const saved = await updateProfileCollectionItem(definition.kind, item.id, payload);
      setItems((current) => current.map((entry) => (entry.id === saved.id ? saved : entry)));
      setEditors((current) => ({
        ...current,
        [saved.id]: collectionItemEditor(definition, saved),
      }));
      onMessage(`${definition.label} ${index + 1} 已保存。`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : `${definition.label}保存失败`);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleDelete(item: ProfileCollectionItem, index: number) {
    const action = `delete-${item.id}`;
    setBusyAction(action);
    onError('');
    try {
      await deleteProfileCollectionItem(definition.kind, item.id);
      const remaining = items
        .filter((entry) => entry.id !== item.id)
        .map((entry, position) => ({ ...entry, position }));
      setItems(remaining);
      setEditors((current) => {
        const next = { ...current };
        delete next[item.id];
        return next;
      });
      onMessage(`${definition.label} ${index + 1} 已删除。`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : `${definition.label}删除失败`);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleMove(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= items.length) return;
    const ids = items.map((item) => item.id);
    [ids[index], ids[target]] = [ids[target], ids[index]];
    const action = `order-${items[index].id}`;
    setBusyAction(action);
    onError('');
    try {
      const reordered = await reorderProfileCollectionItems(definition.kind, ids);
      syncItems(reordered);
      onMessage(`${definition.label}顺序已更新。`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : `${definition.label}排序失败`);
    } finally {
      setBusyAction(null);
    }
  }

  async function handleCreate() {
    setBusyAction('create');
    onError('');
    try {
      const payload = collectionEditorPayload(definition, newEditor);
      const created = await createProfileCollectionItem(definition.kind, payload);
      syncItems([...items, created]);
      setAdding(false);
      setNewEditor({});
      onMessage(`新的${definition.label}已写入 Profile SSOT。`);
    } catch (reason) {
      onError(reason instanceof Error ? reason.message : `${definition.label}新增失败`);
    } finally {
      setBusyAction(null);
    }
  }

  return (
    <section
      className="profile-category profile-collection-section"
      data-testid={`profile-collection-${definition.kind}`}
    >
      <div className="profile-section-heading profile-collection-heading">
        <div>
          <h2>{definition.label}</h2>
          <p>每条记录独立保存、独立审计；顺序会用于后续网申字段映射。</p>
        </div>
        <div className="profile-collection-heading-actions">
          <span className="soft-badge verified">{items.length} 条</span>
          <button
            className="secondary-button"
            type="button"
            aria-label={`新增${definition.label}`}
            onClick={() => {
              setAdding(true);
              setNewEditor({});
            }}
          >
            新增
          </button>
        </div>
      </div>

      {loading ? (
        <p className="profile-empty-note">正在加载{definition.label}…</p>
      ) : items.length === 0 && !adding ? (
        <p className="profile-empty-note">暂无{definition.label}，可手动新增。</p>
      ) : null}

      <div className="profile-collection-list">
        {items.map((item, index) => {
          const values = editors[item.id] ?? {};
          return (
            <article
              className="profile-collection-card"
              data-testid={`profile-collection-${definition.kind}-${item.id}`}
              key={item.id}
            >
              <div className="profile-collection-card-heading">
                <div>
                  <h3>{definition.label} {index + 1}</h3>
                  <span className="soft-badge verified">{collectionSourceLabel(item)}</span>
                </div>
                <span className="profile-collection-id">ID {item.id}</span>
              </div>
              <div className="profile-collection-fields">
                {definition.fields.map((field) => (
                  <CollectionInput
                    ariaPrefix={`${definition.label} ${index + 1}`}
                    field={field}
                    key={field.key}
                    values={values}
                    setValue={(key, value) => updateEditor(item.id, key, value)}
                  />
                ))}
              </div>
              <div className="profile-collection-actions">
                <button
                  className="primary-button"
                  type="button"
                  aria-label={`保存 ${definition.label} ${index + 1}`}
                  disabled={busyAction !== null}
                  onClick={() => handleSave(item, index)}
                >
                  {busyAction === `save-${item.id}` ? '保存中…' : '保存'}
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`上移 ${definition.label} ${index + 1}`}
                  disabled={index === 0 || busyAction !== null}
                  onClick={() => handleMove(index, -1)}
                >
                  上移
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`下移 ${definition.label} ${index + 1}`}
                  disabled={index === items.length - 1 || busyAction !== null}
                  onClick={() => handleMove(index, 1)}
                >
                  下移
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  aria-label={`删除 ${definition.label} ${index + 1}`}
                  disabled={busyAction !== null}
                  onClick={() => handleDelete(item, index)}
                >
                  删除
                </button>
              </div>
            </article>
          );
        })}

        {adding && (
          <article
            className="profile-collection-card profile-collection-card-new"
            data-testid={`profile-collection-new-${definition.kind}`}
          >
            <div className="profile-collection-card-heading">
              <div>
                <h3>新增{definition.label}</h3>
                <span className="soft-badge warning">尚未保存</span>
              </div>
            </div>
            <div className="profile-collection-fields">
              {definition.fields.map((field) => (
                <CollectionInput
                  ariaPrefix={`新增${definition.label}`}
                  field={field}
                  key={field.key}
                  values={newEditor}
                  setValue={(key, value) =>
                    setNewEditor((current) => ({ ...current, [key]: value }))
                  }
                />
              ))}
            </div>
            <div className="profile-collection-actions">
              <button
                className="primary-button"
                type="button"
                aria-label={`保存新增${definition.label}`}
                disabled={busyAction !== null}
                onClick={handleCreate}
              >
                {busyAction === 'create' ? '保存中…' : '保存新增'}
              </button>
              <button
                className="secondary-button"
                type="button"
                aria-label={`取消新增${definition.label}`}
                disabled={busyAction !== null}
                onClick={() => {
                  setAdding(false);
                  setNewEditor({});
                }}
              >
                取消
              </button>
            </div>
          </article>
        )}
      </div>
    </section>
  );
}

function CollectionDraftCard({
  draft,
  index,
  reviewing,
  onAccept,
  onReject,
}: {
  draft: ProfileCollectionDraft;
  index: number;
  reviewing: boolean;
  onAccept: () => void;
  onReject: () => void;
}) {
  return (
    <article className="profile-draft-card">
      <div>
        <div className="badge-row">
          <span className="soft-badge">结构化 · {draft.label}</span>
          <span className="soft-badge verified">
            置信度 {Math.round((draft.confidence ?? 0) * 100)}%
          </span>
        </div>
        <h3>{draft.label}候选 {index + 1}</h3>
        <div className="profile-draft-value">
          {Object.entries(draft.payload).map(([key, value]) => (
            <p key={key}>{displayValue(value)}</p>
          ))}
        </div>
        <p className="profile-draft-source">
          {draft.resume_filename} · V{draft.resume_version_number}
        </p>
      </div>
      <div className="profile-draft-actions">
        <button
          className="primary-button"
          type="button"
          aria-label={`接受 ${draft.label}候选 ${index + 1}`}
          disabled={reviewing}
          onClick={onAccept}
        >
          接受
        </button>
        <button
          className="secondary-button"
          type="button"
          aria-label={`拒绝 ${draft.label}候选 ${index + 1}`}
          disabled={reviewing}
          onClick={onReject}
        >
          拒绝
        </button>
      </div>
    </article>
  );
}

export function ProfilePage() {
  const [definitions, setDefinitions] = useState<ProfileDefinition[]>([]);
  const [fields, setFields] = useState<ProfileField[]>([]);
  const [drafts, setDrafts] = useState<ProfileDraft[]>([]);
  const [collectionDefinitions, setCollectionDefinitions] = useState<ProfileCollectionDefinition[]>([]);
  const [collectionDrafts, setCollectionDrafts] = useState<ProfileCollectionDraft[]>([]);
  const [collectionRefreshVersions, setCollectionRefreshVersions] = useState<Record<string, number>>({});
  const [editValues, setEditValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [savingField, setSavingField] = useState<string | null>(null);
  const [reviewingDraft, setReviewingDraft] = useState<number | null>(null);
  const [reviewingCollectionDraft, setReviewingCollectionDraft] = useState<number | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([
      getProfileDefinitions(),
      getProfileFields(),
      getPendingProfileDrafts(),
      getProfileCollectionDefinitions(),
      getPendingProfileCollectionDrafts(),
    ])
      .then(([
        nextDefinitions,
        nextFields,
        nextDrafts,
        nextCollectionDefinitions,
        nextCollectionDrafts,
      ]) => {
        if (!active) return;
        setDefinitions(nextDefinitions);
        setFields(nextFields);
        setDrafts(nextDrafts);
        setCollectionDefinitions(nextCollectionDefinitions);
        setCollectionDrafts(nextCollectionDrafts);
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
      setEditValues((items) => ({
        ...items,
        [definition.field_key]: valueToEditorText(saved.value),
      }));
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
      setEditValues((items) => ({
        ...items,
        [accepted.field_key]: valueToEditorText(accepted.value),
      }));
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

  async function handleAcceptCollectionDraft(draft: ProfileCollectionDraft) {
    setReviewingCollectionDraft(draft.id);
    setError(null);
    setMessage(null);
    try {
      await acceptProfileCollectionDraft(draft.id);
      setCollectionDrafts((items) => items.filter((item) => item.id !== draft.id));
      setCollectionRefreshVersions((versions) => ({
        ...versions,
        [draft.kind]: (versions[draft.kind] ?? 0) + 1,
      }));
      setMessage(`${draft.label}候选已人工确认并写入 Profile SSOT。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${draft.label}候选确认失败`);
    } finally {
      setReviewingCollectionDraft(null);
    }
  }

  async function handleRejectCollectionDraft(draft: ProfileCollectionDraft) {
    setReviewingCollectionDraft(draft.id);
    setError(null);
    setMessage(null);
    try {
      await rejectProfileCollectionDraft(draft.id);
      setCollectionDrafts((items) => items.filter((item) => item.id !== draft.id));
      setMessage(`${draft.label}候选已拒绝，正式资料未发生变化。`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : `${draft.label}候选拒绝失败`);
    } finally {
      setReviewingCollectionDraft(null);
    }
  }

  const totalPendingDrafts = drafts.length + collectionDrafts.length;

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
          <p>同时加载字段定义、已确认 Profile、结构化集合和待审核的简历候选。</p>
        </article>
      ) : (
        <>
          <section className="profile-review-panel" aria-labelledby="profile-draft-title">
            <div className="profile-section-heading">
              <div>
                <h2 id="profile-draft-title">待审核候选</h2>
                <p>候选值来自简历解析。点击“接受”前，它们不会进入正式 Profile，也不会参与自动填表。</p>
              </div>
              <span className="soft-badge warning">{totalPendingDrafts} 项</span>
            </div>

            {totalPendingDrafts === 0 ? (
              <p className="profile-empty-note">当前没有待审核的简历候选。</p>
            ) : (
              <div className="profile-draft-list">
                {drafts.map((draft) => (
                  <article className="profile-draft-card" key={`scalar-${draft.id}`}>
                    <div>
                      <div className="badge-row">
                        <span className="soft-badge">{draft.category}</span>
                        <span className="soft-badge verified">
                          置信度 {Math.round((draft.confidence ?? 0) * 100)}%
                        </span>
                      </div>
                      <h3>{draft.label}</h3>
                      <p className="profile-draft-value">{displayValue(draft.value)}</p>
                      <p className="profile-draft-source">
                        {draft.resume_filename} · V{draft.resume_version_number}
                      </p>
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

                {collectionDrafts.map((draft, index) => (
                  <CollectionDraftCard
                    draft={draft}
                    index={index}
                    key={`collection-${draft.id}`}
                    reviewing={reviewingCollectionDraft === draft.id}
                    onAccept={() => handleAcceptCollectionDraft(draft)}
                    onReject={() => handleRejectCollectionDraft(draft)}
                  />
                ))}
              </div>
            )}
          </section>

          {collectionDefinitions.length > 0 && (
            <section className="profile-structured-block" aria-labelledby="profile-structured-title">
              <div className="profile-block-heading">
                <p className="eyebrow">Repeatable Profile</p>
                <h2 id="profile-structured-title">结构化经历</h2>
                <p>教育、工作/实习、项目、奖项、证书、语言和技能可保存多条记录，并保留稳定顺序。</p>
              </div>
              <div className="profile-category-list">
                {collectionDefinitions.map((definition) => (
                  <ProfileCollectionSection
                    definition={definition}
                    key={definition.kind}
                    refreshVersion={collectionRefreshVersions[definition.kind] ?? 0}
                    onError={(nextError) => {
                      setMessage(null);
                      setError(nextError || null);
                    }}
                    onMessage={(nextMessage) => {
                      setError(null);
                      setMessage(nextMessage);
                    }}
                  />
                ))}
              </div>
            </section>
          )}

          <section className="profile-structured-block" aria-labelledby="profile-scalar-title">
            <div className="profile-block-heading">
              <p className="eyebrow">Scalar Profile</p>
              <h2 id="profile-scalar-title">基础字段</h2>
              <p>保留现有单值 Profile 兼容层；历史数据和现有自动填表接口继续可用。</p>
            </div>
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
                      const isLongText =
                        definition.multiple || definition.field_key.endsWith('.summary');
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
                                placeholder={
                                  definition.multiple ? '每行填写一项' : `填写${definition.label}`
                                }
                                value={editValues[definition.field_key] ?? ''}
                                onChange={(event) =>
                                  setEditValues((items) => ({
                                    ...items,
                                    [definition.field_key]: event.target.value,
                                  }))
                                }
                              />
                            ) : (
                              <input
                                aria-label={definition.label}
                                type="text"
                                placeholder={`填写${definition.label}`}
                                value={editValues[definition.field_key] ?? ''}
                                onChange={(event) =>
                                  setEditValues((items) => ({
                                    ...items,
                                    [definition.field_key]: event.target.value,
                                  }))
                                }
                              />
                            )}
                          </label>
                          <div className="profile-field-meta">
                            <span className={`soft-badge${field ? ' verified' : ''}`}>
                              {sourceLabel(field)}
                            </span>
                            {field?.updated_at && (
                              <span>更新于 {new Date(field.updated_at).toLocaleString('zh-CN')}</span>
                            )}
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
          </section>
        </>
      )}
    </section>
  );
}
