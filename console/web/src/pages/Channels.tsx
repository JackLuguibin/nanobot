import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card,
  Badge,
  Button,
  Spin,
  Alert,
  Descriptions,
  Tag,
  Empty,
  Space,
  Statistic,
} from 'antd';
import {
  ReloadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
} from '@ant-design/icons';
import * as api from '../api/client';
import { useAppStore } from '../store';

export default function Channels() {
  const queryClient = useQueryClient();
  const { addToast, currentBotId } = useAppStore();
  const [selectedChannel, setSelectedChannel] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState<string | null>(null);

  const { data: channels, isLoading, error, refetch } = useQuery({
    queryKey: ['channels', currentBotId],
    queryFn: () => api.getChannels(currentBotId),
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

  const channelIcons: Record<string, string> = {
    telegram: '📱',
    discord: '💬',
    slack: '💼',
    whatsapp: '📞',
    feishu: '📝',
    dingtalk: '🔔',
    email: '📧',
    qq: '🐧',
    matrix: '🟣',
    mochat: '💬',
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

  const statusBadge = (status: string) => {
    if (status === 'online') return 'success' as const;
    if (status === 'error') return 'error' as const;
    return 'default' as const;
  };

  const selectedChannelData = channels?.find((c) => c.name === selectedChannel);

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

  return (
    <div className="p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            Channels
          </h1>
          <p className="text-sm text-gray-500 mt-1">Manage your communication channels</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {/* Channel Cards Grid */}
      {channels && channels.length > 0 ? (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {channels.map((channel) => (
            <Card
              key={channel.name}
              hoverable
              onClick={() =>
                setSelectedChannel(selectedChannel === channel.name ? null : channel.name)
              }
              className={`cursor-pointer transition-all ${
                selectedChannel === channel.name
                  ? 'border-blue-500 border-2 shadow-md shadow-blue-500/10'
                  : ''
              }`}
              size="small"
            >
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-2xl">{channelIcons[channel.name] || '📱'}</span>
                  <span className="font-medium capitalize">{channel.name}</span>
                </div>
                <Badge status={statusBadge(channel.status)} />
              </div>

              <Space direction="vertical" size={4} className="w-full">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">Status</span>
                  <Tag color={statusColor(channel.status)}>{channel.status}</Tag>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-gray-500">Enabled</span>
                  <Tag color={channel.enabled ? 'success' : 'default'}>
                    {channel.enabled ? 'Yes' : 'No'}
                  </Tag>
                </div>
              </Space>

              {refreshing === channel.name && (
                <div className="mt-3 flex items-center gap-2 text-sm text-blue-600">
                  <ReloadOutlined className="animate-spin" />
                  Refreshing...
                </div>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <Empty description="No channels configured" />
      )}

      {/* Channel Detail Panel */}
      {selectedChannelData && (
        <Card
          title={
            <div className="flex items-center gap-3">
              <span className="text-2xl">{channelIcons[selectedChannelData.name] || '📱'}</span>
              <div>
                <span className="font-semibold capitalize text-lg">
                  {selectedChannelData.name}
                </span>
                <p className="text-xs text-gray-500 font-normal">
                  {channelDescriptions[selectedChannelData.name] || 'Channel'}
                </p>
              </div>
            </div>
          }
          extra={
            <Button
              icon={<ReloadOutlined className={refreshing === selectedChannelData.name ? 'animate-spin' : ''} />}
              loading={refreshing === selectedChannelData.name}
              onClick={() => refreshMutation.mutate(selectedChannelData.name)}
            >
              Refresh
            </Button>
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card size="small" className="bg-gray-50 dark:bg-gray-700/30 border-0">
              <Statistic
                title="Connection Status"
                value={selectedChannelData.status}
                valueStyle={{
                  color:
                    selectedChannelData.status === 'online'
                      ? '#16a34a'
                      : selectedChannelData.status === 'error'
                      ? '#dc2626'
                      : '#9ca3af',
                }}
                prefix={
                  selectedChannelData.status === 'online' ? (
                    <CheckCircleOutlined />
                  ) : selectedChannelData.status === 'error' ? (
                    <CloseCircleOutlined />
                  ) : (
                    <ExclamationCircleOutlined />
                  )
                }
              />
            </Card>

            <Card size="small" className="bg-gray-50 dark:bg-gray-700/30 border-0">
              <Statistic
                title="Configuration"
                value={selectedChannelData.enabled ? 'Enabled' : 'Disabled'}
                valueStyle={{ color: selectedChannelData.enabled ? '#16a34a' : '#9ca3af' }}
                prefix={
                  selectedChannelData.enabled ? (
                    <CheckCircleOutlined />
                  ) : (
                    <CloseCircleOutlined />
                  )
                }
              />
            </Card>

            <Card size="small" className="bg-gray-50 dark:bg-gray-700/30 border-0">
              <div>
                <p className="text-xs text-gray-500 mb-2">Statistics</p>
                {Object.entries(selectedChannelData.stats || {}).length > 0 ? (
                  <div className="space-y-1">
                    {Object.entries(selectedChannelData.stats || {}).map(([key, value]) => (
                      <div key={key} className="flex justify-between text-sm">
                        <span className="text-gray-500 capitalize">{key}:</span>
                        <span className="font-medium">{String(value)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-gray-400 text-sm">No statistics available</p>
                )}
              </div>
            </Card>
          </div>

          <Descriptions
            title="Details"
            size="small"
            bordered
            items={[
              {
                key: 'name',
                label: 'Channel Name',
                children: <span className="capitalize">{selectedChannelData.name}</span>,
              },
              {
                key: 'status',
                label: 'Status',
                children: <Tag color={statusColor(selectedChannelData.status)}>{selectedChannelData.status}</Tag>,
              },
              {
                key: 'enabled',
                label: 'Enabled',
                children: (
                  <Tag color={selectedChannelData.enabled ? 'success' : 'default'}>
                    {selectedChannelData.enabled ? 'Yes' : 'No'}
                  </Tag>
                ),
              },
            ]}
          />

          <Alert
            className="mt-4"
            message="Configuration"
            description={
              <span>
                To configure channels, edit the configuration file at{' '}
                <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                  ~/.nanobot/config.json
                </code>
              </span>
            }
            type="info"
            showIcon
            icon={<InfoCircleOutlined />}
          />
        </Card>
      )}

      {/* Config info when no channel selected */}
      {!selectedChannelData && channels && channels.length > 0 && (
        <Card title="Configuration">
          <Alert
            message={
              <span>
                To configure channels, edit the configuration file at{' '}
                <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                  ~/.nanobot/config.json
                </code>
              </span>
            }
            type="info"
            showIcon
          />
        </Card>
      )}
    </div>
  );
}
