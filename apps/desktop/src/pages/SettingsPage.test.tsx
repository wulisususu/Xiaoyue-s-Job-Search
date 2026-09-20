import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';

import { SettingsPage } from './SettingsPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('offers an OpenCode-like provider picker with Chinese-first presets and custom OpenAI-compatible configuration', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => Promise.resolve(new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } }))),
  );

  render(<SettingsPage />);

  await waitFor(() => expect(screen.getByText('AI 模型与 Provider')).toBeInTheDocument());
  expect(screen.getByText(/远程 Provider 必须使用 HTTPS/)).toBeInTheDocument();
  for (const name of ['DeepSeek', '通义千问', '智谱 GLM', 'Kimi', 'MiniMax', '腾讯混元', 'OpenAI', 'Gemini', 'Grok', 'Mistral', 'OpenRouter', '自定义兼容接口']) {
    expect(screen.getByRole('button', { name: new RegExp(name) })).toBeInTheDocument();
  }

  fireEvent.click(screen.getByRole('button', { name: /智谱 GLM/ }));
  expect(screen.getByLabelText('Base URL')).toHaveValue('https://open.bigmodel.cn/api/paas/v4');
  expect(screen.getByLabelText('模型 ID')).toHaveValue('glm-4.7');

  fireEvent.click(screen.getByRole('button', { name: /Gemini/ }));
  expect(screen.getByLabelText('Base URL')).toHaveValue('https://generativelanguage.googleapis.com/v1beta/openai');
});

it('saves provider settings and secret separately, then tests the saved connection', async () => {
  const calls: Array<{ url: string; method: string; body?: unknown }> = [];
  const saved = {
    id: 'default',
    provider_name: 'DeepSeek',
    base_url: 'https://api.deepseek.com',
    text_model: 'deepseek-flash',
    vision_model: null,
    temperature: 0,
    timeout_seconds: 60,
    supports_json_schema: false,
    supports_vision: false,
    has_api_key: true,
    created_at: '2026-09-19T10:00:00',
    updated_at: '2026-09-19T10:00:00',
  };

  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? 'GET';
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    if (method === 'GET') {
      return Promise.resolve(new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    if (url.endsWith('/api/ai/provider/test')) {
      return Promise.resolve(new Response(JSON.stringify({
        ok: true,
        provider_name: 'DeepSeek',
        model: 'deepseek-flash',
        latency_ms: 86,
      }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
    }
    return Promise.resolve(new Response(JSON.stringify(saved), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  });
  vi.stubGlobal('fetch', fetchMock);

  render(<SettingsPage />);
  await waitFor(() => expect(screen.getByText('AI 模型与 Provider')).toBeInTheDocument());

  fireEvent.click(screen.getByRole('button', { name: /DeepSeek/ }));
  fireEvent.change(screen.getByLabelText('API Key'), { target: { value: 'sk-private' } });
  expect(screen.getByLabelText('API Key')).toHaveAttribute('type', 'password');

  fireEvent.click(screen.getByRole('button', { name: '保存配置' }));
  await waitFor(() => expect(screen.getByText(/配置已保存/)).toBeInTheDocument());

  expect(calls.some((call) => call.url.endsWith('/api/ai/provider') && call.method === 'PUT')).toBe(true);
  expect(calls.some((call) => call.url.endsWith('/api/ai/provider/api-key') && call.method === 'PUT' && (call.body as { api_key?: string })?.api_key === 'sk-private')).toBe(true);

  fireEvent.click(screen.getByRole('button', { name: '测试连接' }));
  await waitFor(() => expect(screen.getByText(/连接成功/)).toBeInTheDocument());
  expect(calls.some((call) => call.url.endsWith('/api/ai/provider/test') && call.method === 'POST')).toBe(true);
});
