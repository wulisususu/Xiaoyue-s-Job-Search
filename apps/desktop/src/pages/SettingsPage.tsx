import { useEffect, useMemo, useState } from 'react';

import {
  deleteAIProviderApiKey,
  getAIProvider,
  saveAIProvider,
  saveAIProviderApiKey,
  testAIProvider,
  type AIProviderConfig,
  type AIProviderWrite,
} from '../api/aiClient';
import {
  DEFAULT_PROVIDER_PRESET,
  PROVIDER_PRESETS,
  matchProviderPreset,
  type ProviderPreset,
  type ProviderRegion,
} from '../ai/providerCatalog';
import '../styles/settings.css';

const REGIONS: ProviderRegion[] = ['中国', '海外', '聚合'];

function formFromPreset(preset: ProviderPreset): AIProviderWrite {
  return {
    provider_name: preset.name,
    base_url: preset.baseUrl,
    text_model: preset.defaultModel,
    vision_model: null,
    temperature: 0,
    timeout_seconds: 60,
    supports_json_schema: preset.supportsJsonSchema,
    supports_vision: preset.supportsVision,
  };
}

function formFromConfig(config: AIProviderConfig): AIProviderWrite {
  return {
    provider_name: config.provider_name,
    base_url: config.base_url,
    text_model: config.text_model,
    vision_model: config.vision_model,
    temperature: config.temperature,
    timeout_seconds: config.timeout_seconds,
    supports_json_schema: config.supports_json_schema,
    supports_vision: config.supports_vision,
  };
}

export function SettingsPage() {
  const [selectedId, setSelectedId] = useState(DEFAULT_PROVIDER_PRESET.id);
  const [form, setForm] = useState<AIProviderWrite>(() => formFromPreset(DEFAULT_PROVIDER_PRESET));
  const [savedConfig, setSavedConfig] = useState<AIProviderConfig | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedPreset = PROVIDER_PRESETS.find((preset) => preset.id === selectedId) ?? DEFAULT_PROVIDER_PRESET;
  const visibleProviders = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return PROVIDER_PRESETS;
    return PROVIDER_PRESETS.filter((preset) =>
      [preset.name, preset.description, preset.region, ...preset.models].join(' ').toLowerCase().includes(needle),
    );
  }, [search]);

  useEffect(() => {
    let active = true;
    getAIProvider()
      .then((config) => {
        if (!active || !config) return;
        const preset = matchProviderPreset(config.provider_name, config.base_url);
        setSelectedId(preset?.id ?? 'custom');
        setForm(formFromConfig(config));
        setSavedConfig(config);
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'AI Provider 配置加载失败');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  function chooseProvider(preset: ProviderPreset) {
    setSelectedId(preset.id);
    setForm(formFromPreset(preset));
    setMessage(null);
    setError(null);
  }

  function patchForm(patch: Partial<AIProviderWrite>) {
    setForm((current) => ({ ...current, ...patch }));
  }

  async function persistConfig(): Promise<AIProviderConfig> {
    const normalized: AIProviderWrite = {
      ...form,
      provider_name: form.provider_name.trim(),
      base_url: form.base_url.trim(),
      text_model: form.text_model.trim(),
      vision_model: form.vision_model?.trim() || null,
    };
    let next = await saveAIProvider(normalized);
    if (apiKey.trim()) {
      next = await saveAIProviderApiKey(apiKey.trim());
      setApiKey('');
    }
    setSavedConfig(next);
    setForm(formFromConfig(next));
    return next;
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const next = await persistConfig();
      setMessage(`配置已保存 · ${next.provider_name} / ${next.text_model}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '保存 AI Provider 失败');
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setError(null);
    setMessage(null);
    try {
      await persistConfig();
      const result = await testAIProvider();
      setMessage(`连接成功 · ${result.model} · ${result.latency_ms} ms`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'AI Provider 连接测试失败');
    } finally {
      setTesting(false);
    }
  }

  async function handleDeleteKey() {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const next = await deleteAIProviderApiKey();
      setSavedConfig(next);
      setMessage('API Key 已从系统凭据存储移除。');
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '删除 API Key 失败');
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="page settings-page">
      <header className="page-header settings-header">
        <div>
          <p className="eyebrow">AI Settings</p>
          <h1>AI 模型与 Provider</h1>
          <p>像 OpenCode 一样先选择提供商，再配置模型与凭据。预设只是起点，Base URL 和模型 ID 始终可以手动覆盖。</p>
        </div>
        <div className={`provider-status ${savedConfig?.has_api_key ? 'ready' : ''}`}>
          <span className="provider-status-dot" />
          {savedConfig?.has_api_key ? '已配置凭据' : '尚未配置'}
        </div>
      </header>

      <div className="provider-workbench">
        <aside className="provider-sidebar" aria-label="AI Provider 列表">
          <div className="provider-search">
            <span aria-hidden="true">⌕</span>
            <input
              aria-label="搜索 Provider"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="搜索 Provider / 模型"
            />
          </div>
          <p className="provider-sidebar-note">中国模型优先 · OpenAI-compatible</p>
          {REGIONS.map((region) => {
            const items = visibleProviders.filter((preset) => preset.region === region);
            if (items.length === 0) return null;
            return (
              <section className="provider-group" key={region}>
                <h2>{region}</h2>
                <div className="provider-list">
                  {items.map((preset) => (
                    <button
                      aria-label={`选择 ${preset.name}`}
                      className={`provider-option ${selectedId === preset.id ? 'active' : ''}`}
                      key={preset.id}
                      onClick={() => chooseProvider(preset)}
                      type="button"
                    >
                      <span className="provider-logo">{preset.shortName}</span>
                      <span className="provider-option-copy">
                        <strong>{preset.name}</strong>
                        <small>{preset.description}</small>
                      </span>
                      <span className="provider-chevron">›</span>
                    </button>
                  ))}
                </div>
              </section>
            );
          })}
        </aside>

        <main className="provider-config">
          <div className="provider-config-hero">
            <span className="provider-logo large">{selectedPreset.shortName}</span>
            <div>
              <div className="provider-title-row">
                <h2>{form.provider_name || selectedPreset.name}</h2>
                <span className="soft-badge">OpenAI-compatible</span>
              </div>
              <p>{selectedPreset.description}</p>
              {selectedPreset.hint && <p className="provider-hint">{selectedPreset.hint}</p>}
            </div>
          </div>

          {loading && <p className="settings-feedback">正在读取本机 AI 配置…</p>}
          {message && <p className="settings-feedback success">{message}</p>}
          {error && <p className="settings-feedback error">{error}</p>}

          <section className="settings-card">
            <div className="settings-section-heading">
              <div>
                <h3>连接</h3>
                <p>凭据单独写入系统凭据库，不进入普通 SQLite 配置表。</p>
              </div>
            </div>

            <div className="settings-form-grid">
              {selectedId === 'custom' && (
                <label className="settings-field span-2">
                  <span>Provider 名称</span>
                  <input
                    value={form.provider_name}
                    onChange={(event) => patchForm({ provider_name: event.target.value })}
                    placeholder="例如：公司网关 / 自建模型"
                  />
                </label>
              )}

              <label className="settings-field span-2">
                <span>Base URL</span>
                <input
                  aria-label="Base URL"
                  value={form.base_url}
                  onChange={(event) => patchForm({ base_url: event.target.value })}
                  placeholder="https://api.example.com/v1"
                  spellCheck={false}
                />
                <small>填写 API 根地址，不要填写 /chat/completions。</small>
              </label>

              <label className="settings-field span-2">
                <span>API Key</span>
                <input
                  aria-label="API Key"
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={savedConfig?.has_api_key ? '已保存在系统凭据库；留空则不修改' : '粘贴 API Key'}
                />
                <small>{savedConfig?.has_api_key ? '当前已有密钥。输入新值会执行安全轮换。' : '保存后界面不会再次回显明文。'}</small>
              </label>
            </div>
          </section>

          <section className="settings-card">
            <div className="settings-section-heading">
              <div>
                <h3>模型</h3>
                <p>可直接使用推荐值，也可以输入服务商控制台里的任意模型 ID。</p>
              </div>
            </div>

            <label className="settings-field">
              <span>模型 ID</span>
              <input
                aria-label="模型 ID"
                list="provider-model-options"
                value={form.text_model}
                onChange={(event) => patchForm({ text_model: event.target.value })}
                placeholder="输入模型 ID"
                spellCheck={false}
              />
              <datalist id="provider-model-options">
                {selectedPreset.models.map((model) => <option value={model} key={model} />)}
              </datalist>
            </label>

            {selectedPreset.models.length > 0 && (
              <div className="model-chips" aria-label="推荐模型">
                {selectedPreset.models.map((model) => (
                  <button
                    className={form.text_model === model ? 'active' : ''}
                    key={model}
                    onClick={() => patchForm({ text_model: model })}
                    type="button"
                  >
                    {model}
                  </button>
                ))}
              </div>
            )}

            <details className="settings-advanced">
              <summary>高级参数</summary>
              <div className="settings-form-grid advanced-grid">
                <label className="settings-field">
                  <span>Temperature</span>
                  <input
                    type="number"
                    min="0"
                    max="2"
                    step="0.1"
                    value={form.temperature}
                    onChange={(event) => patchForm({ temperature: Number(event.target.value) })}
                  />
                </label>
                <label className="settings-field">
                  <span>Timeout（秒）</span>
                  <input
                    type="number"
                    min="5"
                    max="300"
                    value={form.timeout_seconds}
                    onChange={(event) => patchForm({ timeout_seconds: Number(event.target.value) })}
                  />
                </label>
                <label className="settings-field span-2">
                  <span>视觉模型 ID（可选）</span>
                  <input
                    value={form.vision_model ?? ''}
                    onChange={(event) => patchForm({ vision_model: event.target.value || null })}
                    placeholder="留空表示暂不启用视觉模型"
                  />
                </label>
                <label className="settings-toggle">
                  <input
                    type="checkbox"
                    checked={form.supports_json_schema}
                    onChange={(event) => patchForm({ supports_json_schema: event.target.checked })}
                  />
                  <span><strong>JSON Schema</strong><small>仅在服务商确认支持严格 response_format 时开启。</small></span>
                </label>
                <label className="settings-toggle">
                  <input
                    type="checkbox"
                    checked={form.supports_vision}
                    onChange={(event) => patchForm({ supports_vision: event.target.checked })}
                  />
                  <span><strong>Vision</strong><small>为后续 OCR / 图片简历能力保留。</small></span>
                </label>
              </div>
            </details>
          </section>

          <div className="settings-actions">
            <button className="primary-button" disabled={saving || testing} onClick={handleSave} type="button">
              {saving ? '保存中…' : '保存配置'}
            </button>
            <button className="secondary-button" disabled={saving || testing} onClick={handleTest} type="button">
              {testing ? '测试中…' : '测试连接'}
            </button>
            {savedConfig?.has_api_key && (
              <button className="danger-text-button" disabled={saving || testing} onClick={handleDeleteKey} type="button">
                删除 API Key
              </button>
            )}
          </div>
        </main>
      </div>
    </section>
  );
}
