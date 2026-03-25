import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Spin,
  Alert,
  Tag,
  Space,
  Modal,
  Form,
  Input,
  Switch,
  Popconfirm,
} from 'antd';
import {
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  EditOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import {
  Send,
  MessageCircle,
  Briefcase,
  Phone,
  FileText,
  Bell,
  Mail,
  Gamepad2,
  Grid3x3,
  type LucideIcon,
} from 'lucide-react';
import * as api from '../api/client';
import { useAppStore } from '../store';

// Common config fields for token-based channels
const CHANNEL_TOKEN_FIELDS: Record<string, string[]> = {
  telegram: ['token', 'proxy', 'allow_from'],
  discord: ['token', 'allow_from'],
  slack: ['bot_token', 'app_token', 'allow_from'],
  qq: ['app_id', 'secret', 'allow_from'],
  feishu: ['app_id', 'app_secret', 'allow_from'],
  dingtalk: ['client_id', 'client_secret', 'allow_from'],
  whatsapp: ['bridge_url', 'bridge_token', 'allow_from'],
  mochat: ['claw_token', 'agent_user_id', 'allow_from'],
  matrix: ['homeserver', 'user_id', 'access_token', 'device_id', 'allow_from'],
  email: ['imap_host', 'imap_username', 'smtp_host', 'smtp_username', 'from_address', 'allow_from'],
};

function formatAllowFrom(val: unknown): string {
  if (Array.isArray(val)) return val.join(', ');
  if (typeof val === 'string') return val;
  return '';
}

function parseAllowFrom(s: string): string[] {
  return s
    .split(/[,;\s]+/)
    .map((x) => x.trim())
    .filter(Boolean);
}

const CHANNEL_ICONS: Record<string, LucideIcon> = {
  telegram: Send,
  discord: Gamepad2,
  slack: Briefcase,
  whatsapp: Phone,
  feishu: FileText,
  dingtalk: Bell,
  email: Mail,
  qq: MessageCircle,
  matrix: Grid3x3,
  mochat: MessageCircle,
};

function ChannelIcon({ name, size = 24, className }: { name: string; size?: number; className?: string }) {
  const Icon = CHANNEL_ICONS[name] || MessageCircle;
  return <Icon size={size} strokeWidth={1.5} className={className} />;
}

export default function Channels() {
  const queryClient = useQueryClient();
  const { addToast, currentBotId } = useAppStore();
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<string | null>(null);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [editingChannel, setEditingChannel] = useState<string | null>(null);
  const [form] = Form.useForm();

  const { data: channels, isLoading, error, refetch } = useQuery({
    queryKey: ['channels', currentBotId],
    queryFn: () => api.getChannels(currentBotId),
  });

  const { data: config } = useQuery({
    queryKey: ['config', currentBotId],
    queryFn: () => api.getConfig(currentBotId),
    enabled: editModalOpen,
  });

  const refreshMutation = useMutation({
    mutationFn: async (name: string) => {
      setRefreshing(name);
      await new Promise((resolve) => setTimeout(resolve, 1000));
      return { name, success: true, message: 'Refreshed successfully' };
    },
    onSuccess: (result) => {
      addToast({ type: 'success', message: `${result.name} refreshed successfully` });
      queryClient.invalidateQueries({ queryKey: ['channels'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
    onSettled: () => setRefreshing(null),
  });

  const updateMutation = useMutation({
    mutationFn: async ({ name, data }: { name: string; data: Record<string, unknown> }) =>
      api.updateChannel(name, data, currentBotId),
    onSuccess: (_, { name }) => {
      addToast({ type: 'success', message: `Channel ${name} updated` });
      queryClient.invalidateQueries({ queryKey: ['channels'] });
      queryClient.invalidateQueries({ queryKey: ['config'] });
      setEditModalOpen(false);
      setEditingChannel(null);
      form.resetFields();
    },
    onError: (e) => {
      addToast({ type: 'error', message: String(e) });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (name: string) => api.deleteChannel(name, currentBotId),
    onSuccess: (_, name) => {
      addToast({ type: 'success', message: `Channel ${name} disabled` });
      queryClient.invalidateQueries({ queryKey: ['channels'] });
      queryClient.invalidateQueries({ queryKey: ['config'] });
      if (selectedChannel === name) setSelectedChannel(null);
    },
    onError: (e) => {
      addToast({ type: 'error', message: String(e) });
    },
  });

  const channelColors: Record<string, string> = {
    telegram: 'from-sky-500/20 to-blue-500/10',
    discord: 'from-indigo-500/20 to-purple-500/10',
    slack: 'from-amber-500/20 to-orange-500/10',
    whatsapp: 'from-emerald-500/20 to-green-500/10',
    feishu: 'from-blue-500/20 to-cyan-500/10',
    dingtalk: 'from-blue-600/20 to-indigo-500/10',
    email: 'from-slate-500/20 to-gray-500/10',
    qq: 'from-yellow-500/20 to-amber-500/10',
    matrix: 'from-violet-500/20 to-purple-500/10',
    mochat: 'from-teal-500/20 to-emerald-500/10',
  };

  const channelDescriptions: Record<string, string> = {
    telegram: 'Telegram Bot API',
    discord: 'Discord Developer Platform',
    slack: 'Slack App Platform',
    whatsapp: 'WhatsApp Business API',
    feishu: 'Feishu Open Platform',
    dingtalk: 'DingTalk Open API',
    email: 'IMAP/SMTP Email Protocol',
    qq: 'QQ Bot Platform',
    matrix: 'Matrix Open Standard',
    mochat: 'MoChat Enterprise',
  };

  const statusColor = (status: string) => {
    if (status === 'online') return 'success';
    if (status === 'error') return 'error';
    return 'default';
  };

  const selectedChannelData = channels?.find((c) => c.name === selectedChannel);

  const openEditModal = (name: string) => {
    setEditingChannel(name);
    setEditModalOpen(true);
  };

  useEffect(() => {
    if (!editModalOpen || !editingChannel || !config) return;
    const ch = (config.channels as Record<string, Record<string, unknown>>)?.[editingChannel];
    const raw = (ch || {}) as Record<string, unknown>;
    // Support both snake_case and camelCase from config
    const get = (k: string) => raw[k] ?? raw[k.replace(/_([a-z])/g, (_, c) => c.toUpperCase())];
    const fields = CHANNEL_TOKEN_FIELDS[editingChannel] || ['token', 'allow_from'];
    const values: Record<string, unknown> = {
      enabled: get('enabled') !== false,
    };
    for (const f of fields) {
      if (f === 'allow_from') {
        values.allow_from = formatAllowFrom(get('allow_from'));
      } else {
        values[f] = get(f) ?? '';
      }
    }
    form.setFieldsValue(values);
  }, [editModalOpen, editingChannel, config, form]);

  const handleEditSubmit = () => {
    if (!editingChannel) return;
    form.validateFields().then((values) => {
      const data: Record<string, unknown> = {
        enabled: values.enabled,
      };
      const fields = CHANNEL_TOKEN_FIELDS[editingChannel] || ['token', 'allow_from'];
      for (const f of fields) {
        if (f === 'allow_from') {
          const arr = parseAllowFrom(values.allow_from || '');
          if (arr.length > 0) data.allow_from = arr;
        } else if (values[f] !== undefined && values[f] !== '') {
          data[f] = values[f];
        }
      }
      updateMutation.mutate({ name: editingChannel, data });
    });
  };

  const configuredChannels = channels?.filter((c) => c.enabled) ?? [];
  const hasAnyConfigured = configuredChannels.length > 0;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert
          type="error"
          message="Error loading channels"
          description={String(error)}
          showIcon
        />
      </div>
    );
  }

  const sortedChannels = [...(channels || [])].sort((a, b) =>
    a.enabled === b.enabled ? 0 : a.enabled ? -1 : 1
  );

  return (
    <div className="p-6 space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-slate-800 via-slate-700 to-slate-600 dark:from-slate-100 dark:via-slate-200 dark:to-slate-300 bg-clip-text text-transparent">
            Channels
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Manage your communication channels
          </p>
        </div>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => refetch()}
          className="shadow-sm"
        >
          Refresh
        </Button>
      </div>

      {/* Channel Cards Grid */}
      {channels && channels.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {sortedChannels.map((channel) => {
            const accent = channelColors[channel.name] || 'from-slate-500/20 to-slate-400/10';
            const isSelected = selectedChannel === channel.name;
            return (
              <div
                key={channel.name}
                onClick={() =>
                  setSelectedChannel(isSelected ? null : channel.name)
                }
                className={`
                  relative cursor-pointer rounded-xl border-2 transition-all duration-200
                  hover:shadow-lg hover:-translate-y-0.5
                  ${channel.enabled ? 'bg-gradient-to-br ' + accent : 'bg-slate-50/50 dark:bg-slate-800/30'}
                  ${isSelected ? 'border-primary-500 shadow-lg ring-2 ring-primary-500/20' : 'border-slate-200/80 dark:border-slate-700/80 hover:border-slate-300 dark:hover:border-slate-600'}
                  ${!channel.enabled ? 'opacity-85' : ''}
                `}
              >
                {/* Status dot */}
                <div className="absolute top-3 right-3">
                  <span
                    className={`inline-block w-2 h-2 rounded-full ${
                      channel.status === 'online'
                        ? 'bg-emerald-500 animate-pulse'
                        : channel.status === 'error'
                        ? 'bg-red-500'
                        : 'bg-slate-400 dark:bg-slate-500'
                    }`}
                    title={channel.status}
                  />
                </div>

                <div className="p-4">
                  <div className="flex items-center gap-3 mb-3">
                    <div
                      className={`flex items-center justify-center w-12 h-12 rounded-xl text-slate-600 dark:text-slate-400 ${
                        channel.enabled
                          ? 'bg-white/80 dark:bg-slate-800/80 shadow-sm'
                          : 'bg-slate-200/60 dark:bg-slate-700/60'
                      }`}
                    >
                      <ChannelIcon name={channel.name} size={24} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold text-slate-800 dark:text-slate-100 capitalize truncate">
                        {channel.name}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400 truncate">
                        {channelDescriptions[channel.name] || 'Channel'}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center justify-between mb-4">
                    <span
                      className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                        channel.enabled
                          ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
                          : 'bg-slate-200/80 dark:bg-slate-600/50 text-slate-600 dark:text-slate-400'
                      }`}
                    >
                      {channel.enabled ? 'Enabled' : 'Disabled'}
                    </span>
                    {channel.status !== 'offline' && (
                      <Tag color={statusColor(channel.status)} className="text-xs m-0">
                        {channel.status}
                      </Tag>
                    )}
                  </div>

                  {refreshing === channel.name ? (
                    <div className="flex items-center gap-2 text-sm text-primary-600 dark:text-primary-400">
                      <ReloadOutlined className="animate-spin" />
                      Refreshing...
                    </div>
                  ) : (
                    <div className="flex gap-2">
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          openEditModal(channel.name);
                        }}
                        className="flex-1 text-primary-600 hover:text-primary-700 dark:text-primary-400"
                      >
                        Edit
                      </Button>
                      {channel.enabled && (
                        <Popconfirm
                          title="Disable channel?"
                          description="Restart the bot for changes to take effect."
                          onConfirm={(e) => {
                            e?.stopPropagation();
                            deleteMutation.mutate(channel.name);
                          }}
                          okText="Disable"
                          cancelText="Cancel"
                        >
                          <Button
                            type="text"
                            size="small"
                            danger
                            icon={<DeleteOutlined />}
                            onClick={(e) => e.stopPropagation()}
                          >
                            Disable
                          </Button>
                        </Popconfirm>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-xl border-2 border-dashed border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/20 p-16 text-center">
          <p className="text-4xl mb-4">📡</p>
          <p className="text-slate-600 dark:text-slate-400 font-medium">No channels configured</p>
          <p className="text-sm text-slate-500 dark:text-slate-500 mt-1">
            Use Edit on a channel to configure and enable it
          </p>
        </div>
      )}

      {/* Channel Detail Panel */}
      {selectedChannelData && (
        <div
          className={`rounded-xl border-2 overflow-hidden animate-fade-in ${
            selectedChannelData.enabled
              ? 'border-primary-500/30 bg-gradient-to-br ' +
                (channelColors[selectedChannelData.name] || 'from-slate-50 to-slate-100 dark:from-slate-800/50 dark:to-slate-900/50')
              : 'border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/30'
          }`}
        >
          <div className="p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
              <div className="flex items-center gap-4">
                <div className="w-14 h-14 rounded-xl bg-white/80 dark:bg-slate-800/80 shadow-sm flex items-center justify-center text-slate-600 dark:text-slate-400">
                  <ChannelIcon name={selectedChannelData.name} size={28} />
                </div>
                <div>
                  <h2 className="text-xl font-semibold text-slate-800 dark:text-slate-100 capitalize">
                    {selectedChannelData.name}
                  </h2>
                  <p className="text-sm text-slate-500 dark:text-slate-400">
                    {channelDescriptions[selectedChannelData.name] || 'Channel'}
                  </p>
                </div>
              </div>
              <Space wrap>
                <Button
                  type="primary"
                  icon={<EditOutlined />}
                  onClick={() => openEditModal(selectedChannelData.name)}
                >
                  Edit
                </Button>
                {selectedChannelData.enabled && (
                  <Popconfirm
                    title="Disable channel?"
                    description="Restart the bot for changes to take effect."
                    onConfirm={() => deleteMutation.mutate(selectedChannelData.name)}
                    okText="Disable"
                    cancelText="Cancel"
                  >
                    <Button danger icon={<DeleteOutlined />}>
                      Disable
                    </Button>
                  </Popconfirm>
                )}
                <Button
                  icon={<ReloadOutlined className={refreshing === selectedChannelData.name ? 'animate-spin' : ''} />}
                  loading={refreshing === selectedChannelData.name}
                  onClick={() => refreshMutation.mutate(selectedChannelData.name)}
                >
                  Refresh
                </Button>
              </Space>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <div className="rounded-lg bg-white/60 dark:bg-slate-800/60 p-4 border border-slate-200/60 dark:border-slate-700/60">
                <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm mb-1">
                  {selectedChannelData.status === 'online' ? (
                    <CheckCircleOutlined className="text-emerald-500" />
                  ) : selectedChannelData.status === 'error' ? (
                    <CloseCircleOutlined className="text-red-500" />
                  ) : (
                    <ExclamationCircleOutlined className="text-slate-400" />
                  )}
                  Connection
                </div>
                <p className="font-medium text-slate-800 dark:text-slate-100 capitalize">
                  {selectedChannelData.status}
                </p>
              </div>
              <div className="rounded-lg bg-white/60 dark:bg-slate-800/60 p-4 border border-slate-200/60 dark:border-slate-700/60">
                <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm mb-1">
                  {selectedChannelData.enabled ? (
                    <CheckCircleOutlined className="text-emerald-500" />
                  ) : (
                    <CloseCircleOutlined className="text-slate-400" />
                  )}
                  Configuration
                </div>
                <p className="font-medium text-slate-800 dark:text-slate-100">
                  {selectedChannelData.enabled ? 'Enabled' : 'Disabled'}
                </p>
              </div>
              <div className="rounded-lg bg-white/60 dark:bg-slate-800/60 p-4 border border-slate-200/60 dark:border-slate-700/60">
                <div className="text-slate-500 dark:text-slate-400 text-sm mb-1">Statistics</div>
                {Object.entries(selectedChannelData.stats || {}).length > 0 ? (
                  <div className="space-y-1">
                    {Object.entries(selectedChannelData.stats || {}).slice(0, 3).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-sm">
                        <span className="text-slate-500 capitalize">{key}:</span>
                        <span className="font-medium text-slate-800 dark:text-slate-100">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-slate-400 dark:text-slate-500 text-sm">—</p>
                )}
              </div>
            </div>

            <Alert
              message="Configuration changes are saved to config.json. Restart the bot for them to take effect."
              type="info"
              showIcon
              icon={<InfoCircleOutlined />}
              className="rounded-lg"
            />
          </div>
        </div>
      )}

      {/* Edit Channel Modal */}
      <Modal
        title={
          editingChannel ? (
            <span className="flex items-center gap-2">
              <ChannelIcon name={editingChannel} size={20} className="text-slate-600 dark:text-slate-400" />
              <span className="capitalize">Edit {editingChannel}</span>
            </span>
          ) : null
        }
        open={editModalOpen}
        onCancel={() => {
          setEditModalOpen(false);
          setEditingChannel(null);
          form.resetFields();
        }}
        onOk={handleEditSubmit}
        confirmLoading={updateMutation.isPending}
        okText="Save"
        width={520}
        destroyOnHidden
      >
        <Form form={form} layout="vertical" className="mt-4">
          <Form.Item name="enabled" label="Enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
          {editingChannel &&
            (CHANNEL_TOKEN_FIELDS[editingChannel] || ['token', 'allow_from']).map((field) => {
              if (field === 'allow_from') {
                return (
                  <Form.Item
                    key={field}
                    name={field}
                    label="Allow From (comma-separated IDs)"
                    help="Leave empty for public access"
                  >
                    <Input.TextArea rows={2} placeholder="user1, user2, @username" />
                  </Form.Item>
                );
              }
              const isSecret = field.includes('token') || field.includes('secret') || field.includes('password');
              const label = field.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
              return (
                <Form.Item key={field} name={field} label={label}>
                  {isSecret ? (
                    <Input.Password autoComplete="off" placeholder="••••••••" />
                  ) : (
                    <Input placeholder={label} />
                  )}
                </Form.Item>
              );
            })}
        </Form>
      </Modal>

      {/* Hint when no channel selected */}
      {!selectedChannelData && hasAnyConfigured && (
        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          Click a channel card to view details · Use Edit to configure
        </p>
      )}
    </div>
  );
}
