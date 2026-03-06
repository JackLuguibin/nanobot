import { useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../store';
import * as api from '../api/client';
import {
  Card,
  Statistic,
  Button,
  Tag,
  Badge,
  Spin,
  Alert,
  Space,
  List,
  Typography,
  Modal,
} from 'antd';
import {
  ReloadOutlined,
  PoweroffOutlined,
  SyncOutlined,
  ThunderboltOutlined,
  ClockCircleOutlined,
  TeamOutlined,
  MessageOutlined,
  MobileOutlined,
  ApiOutlined,
  CheckCircleOutlined,
} from '@ant-design/icons';

const { Text } = Typography;

function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function formatTimeAgo(dateStr?: string): string {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  const now = new Date();
  const diff = now.getTime() - date.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return 'Just now';
  if (minutes < 60) return `${minutes}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString();
}

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { setStatus, setChannels, setMCPServers, status, addToast } = useAppStore();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['status'],
    queryFn: api.getStatus,
    refetchInterval: 30000,
  });

  const { data: recentSessions } = useQuery({
    queryKey: ['sessions', 'recent'],
    queryFn: async () => {
      const sessions = await api.listSessions();
      return sessions.slice(0, 5);
    },
    refetchInterval: 60000,
  });

  useEffect(() => {
    if (data) {
      setStatus(data);
      setChannels(data.channels || []);
      setMCPServers(data.mcp_servers || []);
    }
  }, [data, setStatus, setChannels, setMCPServers]);

  const stopMutation = useMutation({
    mutationFn: api.stopCurrentTask,
    onSuccess: () => {
      addToast({ type: 'success', message: 'Task stopped successfully' });
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const restartMutation = useMutation({
    mutationFn: api.restartBot,
    onSuccess: () => {
      addToast({ type: 'success', message: 'Bot restart initiated' });
      queryClient.invalidateQueries({ queryKey: ['status'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const handleRestart = () => {
    Modal.confirm({
      title: 'Restart Bot',
      content: 'Are you sure you want to restart the bot?',
      okText: 'Restart',
      onOk: () => restartMutation.mutate(),
    });
  };

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
          message="Error loading status"
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
            Dashboard
          </h1>
          <p className="text-sm text-gray-500 mt-1">Monitor your Nanobot assistant</p>
        </div>
        <Space>
          {status?.running && (
            <Button
              danger
              icon={<PoweroffOutlined />}
              loading={stopMutation.isPending}
              onClick={() => stopMutation.mutate()}
            >
              <span className="hidden sm:inline">Stop</span>
            </Button>
          )}
          <Button
            icon={<SyncOutlined />}
            loading={restartMutation.isPending}
            onClick={handleRestart}
          >
            <span className="hidden sm:inline">Restart</span>
          </Button>
          <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
        </Space>
      </div>

      {/* Stat Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card hoverable>
          <Statistic
            title="Status"
            value={status?.running ? 'Running' : 'Stopped'}
            valueStyle={{ color: status?.running ? '#16a34a' : '#9ca3af' }}
            prefix={
              status?.running ? (
                <Badge status="processing" color="#22c55e" />
              ) : (
                <Badge status="default" />
              )
            }
          />
        </Card>
        <Card hoverable>
          <Statistic
            title="Uptime"
            value={status?.uptime_seconds ? formatUptime(status.uptime_seconds) : '-'}
            prefix={<ClockCircleOutlined className="text-blue-500" />}
          />
        </Card>
        <Card hoverable>
          <Statistic
            title="Active Sessions"
            value={status?.active_sessions ?? 0}
            prefix={<TeamOutlined className="text-purple-500" />}
          />
        </Card>
        <Card hoverable>
          <Statistic
            title="Messages Today"
            value={status?.messages_today ?? 0}
            prefix={<MessageOutlined className="text-orange-500" />}
          />
        </Card>
      </div>

      {/* Model Info */}
      {status?.model && (
        <Card size="small">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-blue-100 dark:bg-blue-900/30">
              <ThunderboltOutlined className="text-blue-600 text-lg" />
            </div>
            <div>
              <Text type="secondary" className="text-xs">
                Current Model
              </Text>
              <p className="font-semibold text-base">{status.model}</p>
            </div>
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Sessions */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <ClockCircleOutlined className="text-purple-500" /> Recent Sessions
            </span>
          }
          size="small"
        >
          <List
            dataSource={recentSessions || []}
            locale={{ emptyText: 'No recent sessions' }}
            renderItem={(session) => (
              <List.Item>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{session.title || session.key}</p>
                  <Text type="secondary" className="text-xs truncate block">
                    {session.last_message || 'No messages'}
                  </Text>
                </div>
                <div className="text-right text-sm text-gray-500 ml-4 flex-shrink-0">
                  <p>{session.message_count} msgs</p>
                  <p className="text-xs">{formatTimeAgo(session.updated_at)}</p>
                </div>
              </List.Item>
            )}
          />
        </Card>

        {/* System Status */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <CheckCircleOutlined className="text-green-500" /> System Status
            </span>
          }
          size="small"
        >
          <div className="space-y-3">
            <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-700/30">
              <span className="flex items-center gap-2 font-medium">
                <MobileOutlined className="text-gray-500" /> Channels
              </span>
              <Space>
                <Text type="secondary" className="text-sm">
                  {status?.channels?.filter((c) => c.status === 'online').length || 0} /{' '}
                  {status?.channels?.length || 0}
                </Text>
                <Badge
                  status={
                    (status?.channels?.length || 0) > 0 &&
                    status?.channels?.some((c) => c.status === 'online')
                      ? 'success'
                      : 'default'
                  }
                />
              </Space>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-700/30">
              <span className="flex items-center gap-2 font-medium">
                <ApiOutlined className="text-gray-500" /> MCP Servers
              </span>
              <Space>
                <Text type="secondary" className="text-sm">
                  {status?.mcp_servers?.filter((m) => m.status === 'connected').length || 0} /{' '}
                  {status?.mcp_servers?.length || 0}
                </Text>
                <Badge
                  status={
                    (status?.mcp_servers?.length || 0) > 0 &&
                    status?.mcp_servers?.some((m) => m.status === 'connected')
                      ? 'success'
                      : 'default'
                  }
                />
              </Space>
            </div>

            <div className="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-gray-700/30">
              <span className="flex items-center gap-2 font-medium">
                <CheckCircleOutlined className="text-gray-500" /> Health
              </span>
              <Tag color={status?.running ? 'success' : 'default'}>
                {status?.running ? 'Healthy' : 'Stopped'}
              </Tag>
            </div>
          </div>
        </Card>
      </div>

      {/* Channels Grid */}
      <Card
        title={
          <span className="flex items-center gap-2">
            <MobileOutlined className="text-blue-500" /> Channels
            <Tag>{status?.channels?.length || 0}</Tag>
          </span>
        }
        size="small"
      >
        {status?.channels && status.channels.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {status.channels.map((channel) => (
              <div
                key={channel.name}
                className="flex flex-col items-center p-4 rounded-xl bg-gray-50 dark:bg-gray-700/30 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
              >
                <Badge
                  status={
                    channel.status === 'online'
                      ? 'success'
                      : channel.status === 'error'
                      ? 'error'
                      : 'default'
                  }
                  className="mb-2"
                />
                <span className="text-sm font-medium capitalize">{channel.name}</span>
                <span className="text-xs text-gray-500 mt-0.5 capitalize">{channel.status}</span>
              </div>
            ))}
          </div>
        ) : (
          <Text type="secondary" className="block text-center py-8">
            No channels configured
          </Text>
        )}
      </Card>

      {/* MCP Servers Grid */}
      <Card
        title={
          <span className="flex items-center gap-2">
            <ApiOutlined className="text-purple-500" /> MCP Servers
            <Tag>{status?.mcp_servers?.length || 0}</Tag>
          </span>
        }
        size="small"
      >
        {status?.mcp_servers && status.mcp_servers.length > 0 ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {status.mcp_servers.map((server) => (
              <div
                key={server.name}
                className="flex flex-col items-center p-4 rounded-xl bg-gray-50 dark:bg-gray-700/30 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
              >
                <Badge
                  status={
                    server.status === 'connected'
                      ? 'success'
                      : server.status === 'error'
                      ? 'error'
                      : 'default'
                  }
                  className="mb-2"
                />
                <span className="text-sm font-medium">{server.name}</span>
                <span className="text-xs text-gray-500 mt-0.5">{server.server_type}</span>
              </div>
            ))}
          </div>
        ) : (
          <Text type="secondary" className="block text-center py-8">
            No MCP servers configured
          </Text>
        )}
      </Card>
    </div>
  );
}
