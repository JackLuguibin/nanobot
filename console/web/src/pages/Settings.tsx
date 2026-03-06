import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Tabs,
  Form,
  Input,
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
} from 'antd';
import {
  SaveOutlined,
  DownloadOutlined,
  KeyOutlined,
  CodeOutlined,
  MobileOutlined,
  ReadOutlined,
  ToolOutlined,
  SunOutlined,
} from '@ant-design/icons';
import { Sun, Moon, Monitor } from 'lucide-react';
import * as api from '../api/client';
import { useAppStore } from '../store';

const { Title, Text } = Typography;

type SettingsTab = 'general' | 'appearance' | 'providers' | 'tools' | 'channels' | 'skills';

interface FormData {
  model: string;
  max_iterations: number;
  temperature: number;
  memory_window: number;
  reasoning_effort: string;
  restrict_to_workspace: boolean;
}

export default function Settings() {
  const queryClient = useQueryClient();
  const { theme, setTheme, addToast } = useAppStore();
  const [activeTab, setActiveTab] = useState<SettingsTab>('general');
  const [form] = Form.useForm<FormData>();

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: api.getConfig,
  });

  useEffect(() => {
    if (config) {
      const agents = (config as Record<string, unknown>).agents as Record<string, unknown> | undefined;
      const tools = (config as Record<string, unknown>).tools as Record<string, unknown> | undefined;
      const defaults = agents?.defaults as Record<string, unknown> | undefined;

      form.setFieldsValue({
        model: (defaults?.model as string) || '',
        max_iterations: (defaults?.max_iterations as number) || 40,
        temperature: (defaults?.temperature as number) || 0.1,
        memory_window: (defaults?.memory_window as number) || 100,
        reasoning_effort: (defaults?.reasoning_effort as string) || 'medium',
        restrict_to_workspace: (tools?.restrictToWorkspace as boolean) || false,
      });
    }
  }, [config, form]);

  const updateConfigMutation = useMutation({
    mutationFn: ({ section, data }: { section: string; data: Record<string, unknown> }) =>
      api.updateConfig(section, data),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Settings saved successfully' });
      queryClient.invalidateQueries({ queryKey: ['config'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const handleSave = async () => {
    const values = await form.validateFields();
    updateConfigMutation.mutate({
      section: 'agents',
      data: {
        defaults: {
          model: values.model,
          max_iterations: values.max_iterations,
          temperature: values.temperature,
          memory_window: values.memory_window,
          reasoning_effort: values.reasoning_effort,
        },
      },
    });
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
  const providers = configRaw?.providers as Record<string, Record<string, unknown>> | undefined;
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

  const tabItems = [
    {
      key: 'general',
      label: (
        <span className="flex items-center gap-1.5">
          <ToolOutlined /> General
        </span>
      ),
      children: (
        <Form form={form} layout="vertical" className="max-w-2xl">
          <Title level={5} className="!mb-4">
            Agent Defaults
          </Title>

          <Form.Item
            label="Model"
            name="model"
            extra="e.g. anthropic/claude-opus-4-5"
          >
            <Input placeholder="anthropic/claude-opus-4-5" size="large" />
          </Form.Item>

          <Form.Item label="Reasoning Effort" name="reasoning_effort">
            <Radio.Group buttonStyle="solid" size="large">
              <Radio.Button value="low">Low</Radio.Button>
              <Radio.Button value="medium">Medium</Radio.Button>
              <Radio.Button value="high">High</Radio.Button>
            </Radio.Group>
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
            <Slider min={1} max={100} marks={{ 1: '1', 50: '50', 100: '100' }} />
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
              marks={{ 0: 'Focused', 1: '1.0', 2: 'Creative' }}
            />
          </Form.Item>

          <Form.Item label="Memory Window" name="memory_window">
            <InputNumber
              min={1}
              max={1000}
              className="w-full"
              addonAfter="messages"
              size="large"
            />
          </Form.Item>
        </Form>
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
        <div className="max-w-2xl">
          <Title level={5} className="!mb-4">
            Theme
          </Title>
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
        </div>
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
        <div className="space-y-6">
          <Title level={5}>Configured Providers</Title>

          {providers && Object.keys(providers).length > 0 ? (
            <div className="space-y-3">
              {Object.entries(providers).map(([name, providerConfig]) => (
                <Card
                  key={name}
                  size="small"
                  className="border-gray-200 dark:border-gray-700"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700">
                        <KeyOutlined className="text-gray-500" />
                      </div>
                      <div>
                        <p className="font-medium capitalize">{name}</p>
                        <Text type="secondary" className="text-xs">
                          {Object.keys(providerConfig).join(', ')}
                        </Text>
                      </div>
                    </div>
                    <Tag color="success">Configured</Tag>
                  </div>
                </Card>
              ))}
            </div>
          ) : (
            <Alert
              message="No providers configured"
              description="Add provider API keys to your configuration file."
              type="info"
              showIcon
              icon={<KeyOutlined />}
            />
          )}

          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <Title level={5} className="!text-sm !mb-3">
              Configuration Format
            </Title>
            <Alert
              message={
                <span>
                  Edit your config file at{' '}
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
  "providers": {
    "openrouter": { "apiKey": "sk-or-v1-xxx" },
    "openai": { "apiKey": "sk-xxx" },
    "anthropic": { "apiKey": "sk-ant-xxx" }
  }
}`}
            </pre>
          </div>
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
        <div className="space-y-6">
          <Title level={5}>Tool Settings</Title>

          <Form form={form} layout="vertical">
            <Card size="small">
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
            </Card>
          </Form>

          <div>
            <Title level={5} className="!text-sm !mb-3">
              Configured MCP Servers
            </Title>
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
                message="No MCP servers configured"
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
        <div className="space-y-6">
          <Title level={5}>Configured Channels</Title>

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
              message="No channels configured"
              description="Add channel configurations to your config file."
              type="info"
              showIcon
              icon={<MobileOutlined />}
            />
          )}

          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <Title level={5} className="!text-sm !mb-3">
              Configuration Format
            </Title>
            <Alert
              message={
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
        </div>
      ),
    },
    {
      key: 'skills',
      label: (
        <span className="flex items-center gap-1.5">
          <ReadOutlined /> Skills
        </span>
      ),
      children: (
        <div className="space-y-6">
          <Title level={5}>Skills Configuration</Title>

          <Alert
            message="How Skills Work"
            description={
              <div className="space-y-2">
                <p>
                  Skills are markdown files that provide additional instructions or knowledge to
                  the agent. Place skill files in:
                </p>
                <code className="block px-3 py-2 bg-gray-100 dark:bg-gray-800 rounded text-sm font-mono">
                  ~/.nanobot/skills/
                </code>
              </div>
            }
            type="info"
            showIcon
            icon={<ReadOutlined />}
          />

          <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
            <Title level={5} className="!text-sm !mb-3">
              Example Skill File
            </Title>
            <pre className="p-5 bg-gray-900 dark:bg-gray-950 rounded-xl overflow-x-auto text-sm text-gray-100 font-mono">
              {`# Coding Assistant

You are a professional software engineer who:
- Writes clean, well-documented code
- Follows best practices and design patterns
- Considers edge cases and error handling
- Provides explanations with examples

When reviewing code, focus on:
1. Correctness and logic
2. Performance implications
3. Security vulnerabilities
4. Maintainability`}
            </pre>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            Settings
          </h1>
          <p className="text-sm text-gray-500 mt-1">Configure your Nanobot preferences</p>
        </div>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={handleExportConfig}>
            Export
          </Button>
          <Button
            type="primary"
            icon={<SaveOutlined />}
            loading={updateConfigMutation.isPending}
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
      />
    </div>
  );
}
