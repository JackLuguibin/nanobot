import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Tabs,
  Form,
  Input,
  AutoComplete,
  InputNumber,
  Slider,
  Switch,
  Button,
  Spin,
  Card,
  Typography,
  Space,
  Radio,
  Tag,
  Alert,
  Collapse,
} from 'antd';
import {
  SaveOutlined,
  DownloadOutlined,
  KeyOutlined,
  CodeOutlined,
  MobileOutlined,
  ToolOutlined,
  SunOutlined,
  EnvironmentOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import { Sun, Moon, Monitor } from 'lucide-react';
import * as api from '../api/client';
import { useAppStore } from '../store';

const { Text } = Typography;

/** Provider names that can be configured in Settings (schema keys, lowercase). */
const PROVIDER_NAMES = [
  'openai',
  'anthropic',
  'openrouter',
  'deepseek',
  'ollama',
  'custom',
  'groq',
  'gemini',
  'azure_openai',
  'vllm',
  'dashscope',
  'zhipu',
  'moonshot',
  'minimax',
  'aihubmix',
  'siliconflow',
  'volcengine',
  'volcengine_coding_plan',
  'byteplus',
  'byteplus_coding_plan',
] as const;

export type ProviderFormEntry = {
  apiKey: string;
  apiBase: string;
  extraHeadersJson: string;
};

/** Match pydantic `to_camel` for provider field names in model_dump(by_alias=True). */
function providerSchemaKeyToJsonKey(snake: string): string {
  const parts = snake.split('_');
  if (parts.length === 1) return parts[0].toLowerCase();
  return (
    parts[0].toLowerCase() +
    parts
      .slice(1)
      .map((p) => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase())
      .join('')
  );
}

function buildProvidersPayload(
  providerForm: Record<string, ProviderFormEntry>
): Record<string, Record<string, unknown>> {
  const out: Record<string, Record<string, unknown>> = {};
  for (const name of PROVIDER_NAMES) {
    const entry = providerForm[name] ?? { apiKey: '', apiBase: '', extraHeadersJson: '' };
    const trimmedJson = entry.extraHeadersJson?.trim() ?? '';
    let extraHeaders: Record<string, string> | null = null;
    if (trimmedJson) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(trimmedJson) as unknown;
      } catch {
        throw new Error(
          `「${name}」的 Extra Headers 不是合法 JSON，请修正后再保存。`
        );
      }
      if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) {
        throw new Error(`「${name}」的 Extra Headers 必须是 JSON 对象（键值均为字符串）。`);
      }
      const obj = parsed as Record<string, unknown>;
      for (const [k, v] of Object.entries(obj)) {
        if (typeof v !== 'string') {
          throw new Error(`「${name}」的 Extra Headers 中 "${k}" 的值必须是字符串。`);
        }
      }
      extraHeaders = obj as Record<string, string>;
    }
    const jsonKey = providerSchemaKeyToJsonKey(name);
    out[jsonKey] = {
      apiKey: entry.apiKey?.trim() ?? '',
      apiBase: entry.apiBase?.trim() ? entry.apiBase.trim() : null,
      extraHeaders,
    };
  }
  return out;
}

type SettingsTab = 'general' | 'appearance' | 'providers' | 'tools' | 'channels' | 'environment';

interface FormData {
  workspace: string;
  model: string;
  provider: string;
  max_tokens: number;
  context_window_tokens: number;
  max_iterations: number;
  temperature: number;
  memory_window: number;
  reasoning_effort: string;
  restrict_to_workspace: boolean;
}

export default function Settings() {
  const queryClient = useQueryClient();
  const { theme, setTheme, addToast, currentBotId } = useAppStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const [form] = Form.useForm<FormData>();

  const { data: config, isLoading } = useQuery({
    queryKey: ['config', currentBotId],
    queryFn: () => api.getConfig(currentBotId),
  });

  const { data: status } = useQuery({
    queryKey: ['status', currentBotId],
    queryFn: () => api.getStatus(currentBotId),
  });

  const { data: envData, isLoading: envLoading } = useQuery({
    queryKey: ['env', currentBotId],
    queryFn: () => api.getEnv(currentBotId),
  });

  const [envEntries, setEnvEntries] = useState<Array<{ key: string; value: string }>>([]);
  useEffect(() => {
    if (envData?.vars) {
      setEnvEntries(
        Object.entries(envData.vars).map(([key, value]) => ({ key, value }))
      );
    } else if (envData && Object.keys(envData.vars || {}).length === 0) {
      setEnvEntries([]);
    }
  }, [envData]);

  const [providerForm, setProviderForm] = useState<Record<string, ProviderFormEntry>>({});
  useEffect(() => {
    const raw = (config as Record<string, unknown>)?.providers as Record<string, Record<string, unknown>> | undefined;
    if (!raw) {
      const empty: ProviderFormEntry = { apiKey: '', apiBase: '', extraHeadersJson: '' };
      setProviderForm(Object.fromEntries(PROVIDER_NAMES.map((name) => [name, empty])));
      return;
    }
    const next: Record<string, ProviderFormEntry> = {};
    for (const name of PROVIDER_NAMES) {
      const p = raw[name] ?? raw[name.replace(/_/g, '')] ?? {};
      const apiKey = (p.apiKey ?? p.api_key ?? '') as string;
      const apiBase = (p.apiBase ?? p.api_base ?? '') as string;
      const extra = p.extraHeaders ?? p.extra_headers;
      const extraHeadersJson =
        typeof extra === 'object' && extra !== null
          ? JSON.stringify(extra, null, 2)
          : typeof extra === 'string'
            ? extra
            : '';
      next[name] = { apiKey, apiBase, extraHeadersJson };
    }
    setProviderForm(next);
  }, [config]);

  useEffect(() => {
    if (config) {
      const agents = (config as Record<string, unknown>).agents as Record<string, unknown> | undefined;
      const tools = (config as Record<string, unknown>).tools as Record<string, unknown> | undefined;
      const defaults = agents?.defaults as Record<string, unknown> | undefined;
      // 后端返回 camelCase (model_dump by_alias)，兼容 snake_case
      const raw = (key: string, camel: string, fallback: number | string) => {
        const d = defaults ?? {};
        return (d[key] ?? d[camel] ?? fallback) as number | string;
      };

      form.setFieldsValue({
        workspace: (defaults?.workspace as string) ?? '~/.nanobot/workspace',
        model: (defaults?.model as string) ?? '',
        provider: (defaults?.provider as string) ?? 'auto',
        max_tokens: Number(raw('maxTokens', 'max_tokens', 8192)),
        context_window_tokens: Number(raw('contextWindowTokens', 'context_window_tokens', 65536)),
        max_iterations: Number(raw('maxToolIterations', 'max_tool_iterations', 40)),
        temperature: Number(raw('temperature', 'temperature', 0.1)),
        memory_window: Number(raw('memoryWindow', 'memory_window', 100)),
        reasoning_effort: (raw('reasoningEffort', 'reasoning_effort', 'medium') as string) || 'medium',
        restrict_to_workspace: (tools?.restrictToWorkspace as boolean) || false,
      });
    }
  }, [config, form]);

  const saveSettingsMutation = useMutation({
    mutationFn: async () => {
      const values = await form.validateFields();
      const providersPayload = buildProvidersPayload(providerForm);
      await api.updateConfig(
        'agents',
        {
          defaults: {
            workspace: values.workspace?.trim() || undefined,
            model: values.model?.trim() || undefined,
            provider: values.provider?.trim() || undefined,
            max_tokens: values.max_tokens,
            context_window_tokens: values.context_window_tokens,
            max_tool_iterations: values.max_iterations,
            temperature: values.temperature,
            memory_window: values.memory_window,
            reasoning_effort: values.reasoning_effort,
          },
        },
        currentBotId
      );
      await api.updateConfig('providers', providersPayload, currentBotId);
      await api.updateConfig(
        'tools',
        { restrictToWorkspace: values.restrict_to_workspace },
        currentBotId
      );
    },
    onSuccess: () => {
      addToast({ type: 'success', message: 'Settings saved successfully' });
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
    onError: (error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      addToast({ type: 'error', message });
    },
  });

  const updateEnvMutation = useMutation({
    mutationFn: (vars: Record<string, string>) => api.updateEnv(vars, currentBotId),
    onSuccess: () => {
      addToast({
        type: 'success',
        message: 'Environment variables saved. Restart the bot for changes to take effect.',
      });
      queryClient.invalidateQueries({ queryKey: ['env'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const handleSave = () => {
    saveSettingsMutation.mutate();
  };

  const handleSaveEnv = () => {
    const vars: Record<string, string> = {};
    for (const { key, value } of envEntries) {
      const k = key?.trim();
      if (k) vars[k] = value ?? '';
    }
    updateEnvMutation.mutate(vars);
  };

  const setProviderField = (
    name: string,
    field: keyof ProviderFormEntry,
    value: string
  ) => {
    setProviderForm((prev) => ({
      ...prev,
      [name]: { ...(prev[name] ?? { apiKey: '', apiBase: '', extraHeadersJson: '' }), [field]: value },
    }));
  };

  const handleExportConfig = () => {
    const configStr = JSON.stringify(config, null, 2);
    const blob = new Blob([configStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nanobot-config.json';
    a.click();
    URL.revokeObjectURL(url);
    addToast({ type: 'success', message: 'Config exported successfully' });
  };

  const configRaw = config as Record<string, unknown> | undefined;
  const channels = configRaw?.channels as Record<string, Record<string, unknown>> | undefined;
  const mcpServers = (configRaw?.tools as Record<string, unknown>)?.mcpServers as
    | Record<string, unknown>
    | undefined;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" />
      </div>
    );
  }

  const envTabContent = (
    <Card
      title="Environment Variables"
      className="max-w-2xl shadow-sm border border-gray-200/80 dark:border-gray-700/80"
    >
      <Alert
        title="These variables are written to .env and loaded when the bot starts."
        description="Restart the bot after saving for changes to take effect. Values are stored as plain text."
        type="info"
        showIcon
        className="mb-4"
      />
      {envLoading ? (
        <Spin />
      ) : (
        <>
          <div className="space-y-2">
            {envEntries.map((entry, idx) => (
              <div key={idx} className="flex gap-2 items-center">
                <Input
                  placeholder="KEY"
                  value={entry.key}
                  onChange={(e) => {
                    const next = [...envEntries];
                    next[idx] = { ...next[idx], key: e.target.value };
                    setEnvEntries(next);
                  }}
                  className="flex-1 font-mono"
                />
                <Input.Password
                  placeholder="value"
                  value={entry.value}
                  onChange={(e) => {
                    const next = [...envEntries];
                    next[idx] = { ...next[idx], value: e.target.value };
                    setEnvEntries(next);
                  }}
                  className="flex-1 font-mono"
                />
                <Button
                  type="text"
                  danger
                  icon={<DeleteOutlined />}
                  onClick={() => setEnvEntries(envEntries.filter((_, i) => i !== idx))}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2">
            <Button
              icon={<PlusOutlined />}
              onClick={() => setEnvEntries([...envEntries, { key: '', value: '' }])}
            >
              Add Variable
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={updateEnvMutation.isPending}
              onClick={handleSaveEnv}
            >
              Save Environment
            </Button>
          </div>
        </>
      )}
    </Card>
  );

  const tabItems = [
    {
      key: 'general',
      label: (
        <span className="flex items-center gap-1.5">
          <ToolOutlined /> General
        </span>
      ),
      children: (
        <Card
          title="Agent Defaults"
          className="shadow-sm border border-gray-200/80 dark:border-gray-700/80"
          styles={{ body: { paddingTop: 4 } }}
        >
          <Form form={form} layout="vertical" className="max-w-xl">
            <Form.Item
              label="Model"
              name="model"
              extra="Select a suggested model or type provider/model (e.g. anthropic/claude-opus-4-5)"
            >
              <AutoComplete
                size="large"
                placeholder="e.g. anthropic/claude-opus-4-5, deepseek-v3.2"
                options={[
                  ...(status?.model ? [{ value: status.model }] : []),
                  { value: 'anthropic/claude-opus-4-5' },
                  { value: 'openai/gpt-4o' },
                  { value: 'deepseek-v3.2' },
                  { value: 'deepseek/deepseek-chat' },
                  { value: 'openrouter/openai/gpt-4o' },
                ].filter((o, i, arr) => arr.findIndex((x) => x.value === o.value) === i)}
                filterOption={(input, option) =>
                  (option?.value ?? '').toLowerCase().includes((input || '').toLowerCase())
                }
              />
            </Form.Item>

            <Form.Item
              label="Provider"
              name="provider"
              extra="Select a LLM provider or leave as 'auto' for automatic detection"
            >
              <AutoComplete
                size="large"
                placeholder="e.g. auto, anthropic, openai, deepseek"
                options={[
                  { value: 'auto' },
                  ...PROVIDER_NAMES.map((p) => ({ value: p })),
                ].filter((o, i, arr) => arr.findIndex((x) => x.value === o.value) === i)}
                filterOption={(input, option) =>
                  (option?.value ?? '').toLowerCase().includes((input || '').toLowerCase())
                }
              />
            </Form.Item>

            <Form.Item label="Reasoning Effort" name="reasoning_effort">
              <Radio.Group buttonStyle="solid" size="large">
                <Radio.Button value="low">Low</Radio.Button>
                <Radio.Button value="medium">Medium</Radio.Button>
                <Radio.Button value="high">High</Radio.Button>
              </Radio.Group>
            </Form.Item>

            <Form.Item
              label="Workspace"
              name="workspace"
              extra="Directory for bot workspace files (e.g. ~/.nanobot/workspace)"
            >
              <Input placeholder="~/.nanobot/workspace" size="large" />
            </Form.Item>

            <Form.Item
              label={
                <span>
                  Max Tokens{' '}
                  <Text type="secondary" className="text-xs font-normal">
                    (1 – 200000)
                  </Text>
                </span>
              }
              name="max_tokens"
            >
              <InputNumber min={1} max={200000} className="w-full max-w-[200px]" size="large" />
            </Form.Item>

            <Form.Item
              label={
                <span>
                  Context Window Tokens{' '}
                  <Text type="secondary" className="text-xs font-normal">
                    (1 – 1000000)
                  </Text>
                </span>
              }
              name="context_window_tokens"
            >
              <InputNumber min={1} max={1000000} className="w-full max-w-[200px]" size="large" />
            </Form.Item>

            <Form.Item
              label={
                <span>
                  Max Iterations{' '}
                  <Text type="secondary" className="text-xs font-normal">
                    (1 – 100)
                  </Text>
                </span>
              }
              name="max_iterations"
            >
              <Slider min={1} max={100} marks={{ 1: '1', 50: '50', 100: '100' }} tooltip={{ formatter: (v) => (v !== undefined ? v : '') }} />
            </Form.Item>

            <Form.Item
              label={
                <span>
                  Temperature{' '}
                  <Text type="secondary" className="text-xs font-normal">
                    (0.0 – 2.0)
                  </Text>
                </span>
              }
              name="temperature"
            >
              <Slider
                min={0}
                max={2}
                step={0.1}
                marks={{ 0: '0.0', 1: '1.0', 2: '2.0' }}
                tooltip={{ formatter: (v) => (v !== undefined ? v.toFixed(1) : '') }}
              />
            </Form.Item>

            <Form.Item label="Memory Window" name="memory_window">
              <Space.Compact size="large">
                <InputNumber min={1} max={1000} className="w-full max-w-[180px]" />
                <Input readOnly value="messages" className="!w-[100px] !pointer-events-none !select-none" />
              </Space.Compact>
            </Form.Item>
          </Form>
        </Card>
      ),
    },
    {
      key: 'appearance',
      label: (
        <span className="flex items-center gap-1.5">
          <SunOutlined /> Appearance
        </span>
      ),
      children: (
        <Card
          title="Theme"
          className="max-w-2xl shadow-sm border border-gray-200/80 dark:border-gray-700/80"
        >
          <div className="grid grid-cols-3 gap-4">
            {[
              { value: 'light', Icon: Sun, label: 'Light', desc: 'Clean and bright' },
              { value: 'dark', Icon: Moon, label: 'Dark', desc: 'Easy on the eyes' },
              { value: 'system', Icon: Monitor, label: 'System', desc: 'Follow OS setting' },
            ].map((option) => (
              <Card
                key={option.value}
                hoverable
                onClick={() => setTheme(option.value as 'light' | 'dark' | 'system')}
                className={`cursor-pointer text-center transition-all ${
                  theme === option.value ? 'border-blue-500 border-2 shadow-md' : ''
                }`}
              >
                <div
                  className={`inline-flex items-center justify-center w-12 h-12 rounded-xl mb-3 ${
                    theme === option.value
                      ? 'bg-blue-100 dark:bg-blue-900/30'
                      : 'bg-gray-100 dark:bg-gray-700'
                  }`}
                >
                  <option.Icon
                    className={`w-6 h-6 ${
                      theme === option.value ? 'text-blue-600' : 'text-gray-500'
                    }`}
                  />
                </div>
                <div
                  className={`font-medium text-sm ${
                    theme === option.value ? 'text-blue-600 dark:text-blue-400' : ''
                  }`}
                >
                  {option.label}
                </div>
                <Text type="secondary" className="text-xs">
                  {option.desc}
                </Text>
              </Card>
            ))}
          </div>
        </Card>
      ),
    },
    {
      key: 'providers',
      label: (
        <span className="flex items-center gap-1.5">
          <KeyOutlined /> Providers
        </span>
      ),
      children: (
        <div className="max-w-2xl space-y-4">
          <Card
            title="API Key / API Base"
            className="shadow-sm border border-gray-200/80 dark:border-gray-700/80"
            styles={{ body: { paddingTop: 0 } }}
          >
            <Alert
              title="Sensitive"
              description="API keys are stored in your config file. Restart the bot for provider changes to take effect."
              type="warning"
              showIcon
              className="mb-4"
            />
            <Collapse
            defaultActiveKey={[]}
            items={PROVIDER_NAMES.map((name) => {
              const entry = providerForm[name] ?? { apiKey: '', apiBase: '', extraHeadersJson: '' };
              const hasKey = Boolean(entry.apiKey?.trim());
              return {
                key: name,
                label: (
                  <span className="flex items-center gap-2">
                    <span className="font-medium capitalize">{name.replace(/_/g, ' ')}</span>
                    {hasKey && <Tag color="success">Configured</Tag>}
                  </span>
                ),
                children: (
                  <div className="grid grid-cols-1 gap-3 pt-1">
                    <div>
                      <label className="block text-sm font-medium mb-1">API Key</label>
                      <Input.Password
                        placeholder="sk-..."
                        value={entry.apiKey}
                        onChange={(e) => setProviderField(name, 'apiKey', e.target.value)}
                        className="font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1">API Base (optional)</label>
                      <Input
                        placeholder="https://api.example.com/v1"
                        value={entry.apiBase}
                        onChange={(e) => setProviderField(name, 'apiBase', e.target.value)}
                        className="font-mono"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1">
                        Extra Headers (optional, JSON)
                      </label>
                      <Input.TextArea
                        placeholder='{"X-Custom-Header": "value"}'
                        value={entry.extraHeadersJson}
                        onChange={(e) => setProviderField(name, 'extraHeadersJson', e.target.value)}
                        rows={2}
                        className="font-mono text-sm"
                      />
                    </div>
                  </div>
                ),
              };
            })}
            />
          </Card>
        </div>
      ),
    },
    {
      key: 'tools',
      label: (
        <span className="flex items-center gap-1.5">
          <CodeOutlined /> Tools
        </span>
      ),
      children: (
        <div className="max-w-2xl space-y-6">
          <Card
            title="Tool Settings"
            className="shadow-sm border border-gray-200/80 dark:border-gray-700/80"
          >
          <Form form={form} layout="vertical">
            <div className="rounded-lg bg-gray-50 dark:bg-gray-800/50 p-4 border border-gray-100 dark:border-gray-700/50">
              <div className="flex items-center justify-between">
                <div className="flex-1 pr-4">
                  <p className="font-medium">Restrict to Workspace</p>
                  <Text type="secondary" className="text-sm">
                    When enabled, all file and shell operations are restricted to the workspace
                    directory
                  </Text>
                </div>
                <Form.Item name="restrict_to_workspace" valuePropName="checked" className="!mb-0">
                  <Switch />
                </Form.Item>
              </div>
            </div>
          </Form>
          </Card>

          <Card
            title="Configured MCP Servers"
            size="small"
            className="shadow-sm border border-gray-200/80 dark:border-gray-700/80"
          >
          <div className="pt-1">
            {mcpServers && Object.keys(mcpServers).length > 0 ? (
              <div className="space-y-2">
                {Object.entries(mcpServers).map(([name, serverConfig]) => {
                  const sc = serverConfig as Record<string, unknown>;
                  return (
                    <Card key={name} size="small">
                      <div className="flex items-center gap-3">
                        <CodeOutlined className="text-gray-500" />
                        <div>
                          <p className="font-medium">{name}</p>
                          <Text type="secondary" className="text-xs font-mono">
                            {sc.command
                              ? `${sc.command} ${Array.isArray(sc.args) ? (sc.args as string[]).join(' ') : ''}`
                              : String(sc.url || '')}
                          </Text>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            ) : (
              <Alert
                title="No MCP servers configured"
                description={
                  <span>
                    Configure MCP servers in your config file under{' '}
                    <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                      tools.mcpServers
                    </code>
                  </span>
                }
                type="info"
                showIcon
              />
            )}
          </div>
          </Card>
        </div>
      ),
    },
    {
      key: 'channels',
      label: (
        <span className="flex items-center gap-1.5">
          <MobileOutlined /> Channels
        </span>
      ),
      children: (
        <div className="max-w-2xl space-y-6">
          <Card
            title="Configured Channels"
            className="shadow-sm border border-gray-200/80 dark:border-gray-700/80"
          >
          {channels && Object.keys(channels).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(channels).map(([name, channelConfig]) => {
                const enabled = (channelConfig as Record<string, unknown>).enabled !== false;
                return (
                  <Card key={name} size="small">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <MobileOutlined className="text-gray-500" />
                        <div>
                          <p className="font-medium capitalize">{name}</p>
                          <Text type="secondary" className="text-xs">
                            {Object.keys(channelConfig)
                              .filter((k) => k !== 'enabled')
                              .join(', ') || 'Default config'}
                          </Text>
                        </div>
                      </div>
                      <Tag color={enabled ? 'success' : 'default'}>
                        {enabled ? 'Enabled' : 'Disabled'}
                      </Tag>
                    </div>
                  </Card>
                );
              })}
            </div>
            ) : (
              <Alert
                title="No channels configured"
                description="Add channel configurations to your config file."
                type="info"
                showIcon
                icon={<MobileOutlined />}
              />
          )}
          </Card>

          <Card
            title="Configuration Format"
            size="small"
            className="shadow-sm border border-gray-200/80 dark:border-gray-700/80"
          >
          <div className="pt-1">
            <Alert
              title={
                <span>
                  Configure channels in your config file at{' '}
                  <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                    ~/.nanobot/config.json
                  </code>
                </span>
              }
              type="info"
              className="mb-3"
            />
            <pre className="p-5 bg-gray-900 dark:bg-gray-950 rounded-xl overflow-x-auto text-sm text-gray-100 font-mono">
              {`{
  "channels": {
    "telegram": { "enabled": true, "token": "YOUR_BOT_TOKEN" },
    "discord": { "enabled": true, "token": "YOUR_DISCORD_TOKEN" }
  }
}`}
            </pre>
          </div>
          </Card>
        </div>
      ),
    },
    {
      key: 'environment',
      label: (
        <span className="flex items-center gap-1.5">
          <EnvironmentOutlined /> Environment
        </span>
      ),
      children: envTabContent,
    },
  ];

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            Settings
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5">
            Configure your Nanobot preferences
          </p>
        </div>
        <Space wrap>
          <Button icon={<DownloadOutlined />} onClick={handleExportConfig}>
            Export
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={saveSettingsMutation.isPending}
            onClick={handleSave}
          >
            Save Changes
          </Button>
        </Space>
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as SettingsTab)}
        items={tabItems}
        className="settings-tabs [&_.ant-slider-track]:h-2 [&_.ant-slider-rail]:h-2"
      />
    </div>
  );
}
