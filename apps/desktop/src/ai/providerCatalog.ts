export type ProviderRegion = '中国' | '海外' | '聚合';

export interface ProviderPreset {
  id: string;
  name: string;
  shortName: string;
  region: ProviderRegion;
  description: string;
  baseUrl: string;
  models: string[];
  defaultModel: string;
  supportsJsonSchema: boolean;
  supportsVision: boolean;
  hint?: string;
}

export const PROVIDER_PRESETS: ProviderPreset[] = [
  {
    id: 'deepseek',
    name: 'DeepSeek',
    shortName: 'DS',
    region: '中国',
    description: '深度求索官方 API，OpenAI-compatible。',
    baseUrl: 'https://api.deepseek.com',
    models: ['deepseek-flash', 'deepseek-v4-pro'],
    defaultModel: 'deepseek-flash',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'qwen',
    name: '通义千问',
    shortName: 'QW',
    region: '中国',
    description: '阿里云百炼 DashScope OpenAI 兼容接口。',
    baseUrl: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: ['qwen-plus', 'qwen-max', 'qwen3-coder-plus'],
    defaultModel: 'qwen-plus',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'zhipu',
    name: '智谱 GLM',
    shortName: 'GLM',
    region: '中国',
    description: '智谱 BigModel OpenAI-compatible API。',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    models: ['glm-4.7', 'glm-4.5'],
    defaultModel: 'glm-4.7',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'kimi',
    name: 'Kimi',
    shortName: 'KM',
    region: '中国',
    description: 'Moonshot AI，支持直接填写最新 Kimi 模型 ID。',
    baseUrl: 'https://api.moonshot.cn/v1',
    models: ['kimi-k2.5', 'moonshot-v1-128k'],
    defaultModel: 'kimi-k2.5',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'minimax',
    name: 'MiniMax',
    shortName: 'MM',
    region: '中国',
    description: 'MiniMax 开放平台 OpenAI-compatible 接入。',
    baseUrl: 'https://api.minimax.io/v1',
    models: ['MiniMax-M3', 'MiniMax-M2.5'],
    defaultModel: 'MiniMax-M3',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'hunyuan',
    name: '腾讯混元',
    shortName: 'HY',
    region: '中国',
    description: '腾讯混元 OpenAI 兼容接口。',
    baseUrl: 'https://api.hunyuan.cloud.tencent.com/v1',
    models: ['hy3-preview', 'hunyuan-turbos-latest'],
    defaultModel: 'hy3-preview',
    supportsJsonSchema: false,
    supportsVision: false,
    hint: '腾讯旧平台正在向 TokenHub 迁移；如控制台给出新地址，可直接覆盖 Base URL。',
  },
  {
    id: 'doubao',
    name: '火山方舟 / 豆包',
    shortName: 'DB',
    region: '中国',
    description: '火山方舟 API；模型 ID 以控制台实际开放值为准。',
    baseUrl: 'https://ark.cn-beijing.volces.com/api/v3',
    models: ['doubao-seed-2-0-lite-260215'],
    defaultModel: 'doubao-seed-2-0-lite-260215',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'siliconflow',
    name: 'SiliconFlow',
    shortName: 'SF',
    region: '中国',
    description: '硅基流动聚合模型 API，可直接填写平台模型 ID。',
    baseUrl: 'https://api.siliconflow.cn/v1',
    models: ['deepseek-ai/DeepSeek-V3.2', 'Qwen/Qwen3-235B-A22B'],
    defaultModel: 'deepseek-ai/DeepSeek-V3.2',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'openai',
    name: 'OpenAI',
    shortName: 'OA',
    region: '海外',
    description: 'OpenAI 官方 API。',
    baseUrl: 'https://api.openai.com/v1',
    models: ['gpt-5.2', 'gpt-5.1'],
    defaultModel: 'gpt-5.2',
    supportsJsonSchema: true,
    supportsVision: false,
  },
  {
    id: 'gemini',
    name: 'Gemini',
    shortName: 'G',
    region: '海外',
    description: 'Google Gemini 的 OpenAI compatibility endpoint。',
    baseUrl: 'https://generativelanguage.googleapis.com/v1beta/openai',
    models: ['gemini-3.8-flash', 'gemini-3-pro'],
    defaultModel: 'gemini-3.8-flash',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'grok',
    name: 'Grok',
    shortName: 'X',
    region: '海外',
    description: 'xAI OpenAI-compatible API。',
    baseUrl: 'https://api.x.ai/v1',
    models: ['grok-4', 'grok-4-fast'],
    defaultModel: 'grok-4',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'mistral',
    name: 'Mistral',
    shortName: 'MI',
    region: '海外',
    description: 'Mistral AI 官方 OpenAI-compatible API。',
    baseUrl: 'https://api.mistral.ai/v1',
    models: ['mistral-large-latest', 'codestral-latest'],
    defaultModel: 'mistral-large-latest',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'openrouter',
    name: 'OpenRouter',
    shortName: 'OR',
    region: '聚合',
    description: '一个 Key 访问多家模型，包括 Claude / Gemini / GPT 等。',
    baseUrl: 'https://openrouter.ai/api/v1',
    models: ['openai/gpt-5.2', 'anthropic/claude-sonnet-4-5', 'google/gemini-3-pro'],
    defaultModel: 'anthropic/claude-sonnet-4-5',
    supportsJsonSchema: false,
    supportsVision: false,
  },
  {
    id: 'custom',
    name: '自定义兼容接口',
    shortName: '{}',
    region: '聚合',
    description: '任何支持 OpenAI /chat/completions 协议的网关或代理。',
    baseUrl: '',
    models: [],
    defaultModel: '',
    supportsJsonSchema: false,
    supportsVision: false,
  },
];

export const DEFAULT_PROVIDER_PRESET = PROVIDER_PRESETS[0];

export function matchProviderPreset(providerName: string, baseUrl: string): ProviderPreset | undefined {
  const normalizedUrl = baseUrl.replace(/\/$/, '').toLowerCase();
  return PROVIDER_PRESETS.find((preset) => (
    preset.id !== 'custom'
    && (
      preset.name.toLowerCase() === providerName.trim().toLowerCase()
      || (preset.baseUrl && preset.baseUrl.replace(/\/$/, '').toLowerCase() === normalizedUrl)
    )
  ));
}
