import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import {
  Card,
  Statistic,
  Table,
  Tag,
  Spin,
  Empty,
  Space,
  Typography,
  Select,
  Badge,
} from 'antd';
import {
  SyncOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  CloudServerOutlined,
  RobotOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  PauseCircleOutlined,
} from '@ant-design/icons';
import { useAppStore } from '../store';
import { getWSRef } from '../hooks/useWebSocket';
import * as api from '../api/client';
import type { QueueStatus } from '../api/types_queue';

const { Text } = Typography;

function getInboundColor(size: number): string {
  if (size === 0) return '#22c55e';
  if (size <= 3) return '#f59e0b';
  return '#ef4444';
}

function getOutboundColor(size: number): string {
  if (size === 0) return '#22c55e';
  if (size <= 2) return '#f59e0b';
  return '#ef4444';
}

function SocketStatusBadge({ connected }: { connected: boolean }) {
  if (connected) {
    return (
      <Badge status="success" text={<Text className="text-xs text-green-600 dark:text-green-400">Connected</Text>} />
    );
  }
  return (
    <Badge status="error" text={<Text className="text-xs text-red-500">Disconnected</Text>} />
  );
}

function BotQueueCard({ botId }: { botId: string }) {
  const queryClient = useQueryClient();
  const status = queryClient.getQueryData<QueueStatus>(['queue-status', botId]);

  if (!status) {
    return (
      <Card className="rounded-xl">
        <div className="flex items-center justify-center h-32">
          <Spin />
        </div>
      </Card>
    );
  }

  const channelQueue = status.channel_queue;
  const zmqQueue = status.zmq_queue;

  const subSocketColumns = [
    {
      title: 'Agent',
      dataIndex: 'agent_id',
      key: 'agent_id',
      render: (id: string) => (
        <Text className="font-mono text-xs">{id}</Text>
      ),
    },
    {
      title: 'Bot',
      dataIndex: 'bot_id',
      key: 'bot_id',
      render: (id: string) => <Tag color="blue">{id}</Tag>,
    },
    {
      title: 'Address',
      dataIndex: 'address',
      key: 'address',
      render: (addr: string) => (
        <Text className="text-xs text-gray-500 dark:text-gray-400 font-mono">{addr}</Text>
      ),
    },
    {
      title: 'Status',
      dataIndex: 'connected',
      key: 'connected',
      render: (connected: boolean) => <SocketStatusBadge connected={connected} />,
    },
  ];

  return (
    <Card
      className="rounded-xl"
      title={
        <div className="flex items-center gap-2">
          <RobotOutlined className="text-blue-500" />
          <span className="font-semibold">{botId}</span>
          {status.last_updated && (
            <Text type="secondary" className="text-xs ml-auto">
              Updated {new Date(status.last_updated).toLocaleTimeString()}
            </Text>
          )}
        </div>
      }
      extra={
        status.last_updated && (
          <Text type="secondary" className="text-xs">
            Updated {new Date(status.last_updated).toLocaleTimeString()}
          </Text>
        )
      }
    >
      {/* Channel Layer */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <CloudServerOutlined className="text-cyan-500" />
          <Text strong className="text-sm">Channel Layer (asyncio.Queue)</Text>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Card
            size="small"
            className="rounded-lg border-0 bg-gray-50 dark:bg-gray-800/40"
          >
            <Statistic
              title={
                <span className="flex items-center gap-1.5">
                  <ArrowDownOutlined className="text-blue-500 text-xs" />
                  Inbound Queue
                </span>
              }
              value={channelQueue.inbound_size}
              styles={{
                content: {
                  color: getInboundColor(channelQueue.inbound_size),
                  fontSize: '2rem',
                  fontWeight: 700,
                },
              }}
              suffix={
                channelQueue.inbound_size === 0 ? (
                  <CheckCircleOutlined className="text-green-500 text-sm ml-1" />
                ) : (
                  <PauseCircleOutlined className="text-amber-500 text-sm ml-1" />
                )
              }
            />
            <Text type="secondary" className="text-xs block mt-1">
              {channelQueue.inbound_size === 0
                ? 'No pending messages'
                : `${channelQueue.inbound_size} message${channelQueue.inbound_size > 1 ? 's' : ''} waiting`}
            </Text>
          </Card>
          <Card
            size="small"
            className="rounded-lg border-0 bg-gray-50 dark:bg-gray-800/40"
          >
            <Statistic
              title={
                <span className="flex items-center gap-1.5">
                  <ArrowUpOutlined className="text-orange-500 text-xs" />
                  Outbound Queue
                </span>
              }
              value={channelQueue.outbound_size}
              styles={{
                content: {
                  color: getOutboundColor(channelQueue.outbound_size),
                  fontSize: '2rem',
                  fontWeight: 700,
                },
              }}
              suffix={
                channelQueue.outbound_size === 0 ? (
                  <CheckCircleOutlined className="text-green-500 text-sm ml-1" />
                ) : (
                  <PauseCircleOutlined className="text-amber-500 text-sm ml-1" />
                )
              }
            />
            <Text type="secondary" className="text-xs block mt-1">
              {channelQueue.outbound_size === 0
                ? 'No pending messages'
                : `${channelQueue.outbound_size} message${channelQueue.outbound_size > 1 ? 's' : ''} waiting`}
            </Text>
          </Card>
        </div>
      </div>

      {/* Agent Layer */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <RobotOutlined className="text-purple-500" />
          <Text strong className="text-sm">Agent Layer (ZeroMQ Bus)</Text>
          {!zmqQueue.is_initialized && (
            <Tag color="default" className="ml-2">Not Initialized</Tag>
          )}
        </div>

        {zmqQueue.is_initialized ? (
          <>
            {/* ZMQ Socket Overview */}
            <div className="grid grid-cols-2 gap-3 mb-4">
              {zmqQueue.pub_socket && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/40">
                  <div className="flex flex-col">
                    <Text className="text-xs text-gray-500 dark:text-gray-400">PUB Socket</Text>
                    <Text className="text-xs font-mono">{zmqQueue.pub_socket.address}</Text>
                  </div>
                  <div className="ml-auto">
                    {zmqQueue.pub_socket.connected ? (
                      <CheckCircleOutlined className="text-green-500 text-lg" />
                    ) : (
                      <CloseCircleOutlined className="text-red-500 text-lg" />
                    )}
                  </div>
                </div>
              )}
              {zmqQueue.router_socket && (
                <div className="flex items-center gap-2 p-3 rounded-lg bg-purple-50 dark:bg-purple-900/20 border border-purple-100 dark:border-purple-800/40">
                  <div className="flex flex-col">
                    <Text className="text-xs text-gray-500 dark:text-gray-400">ROUTER Socket</Text>
                    <Text className="text-xs font-mono">{zmqQueue.router_socket.address}</Text>
                  </div>
                  <div className="ml-auto">
                    {zmqQueue.router_socket.connected ? (
                      <CheckCircleOutlined className="text-green-500 text-lg" />
                    ) : (
                      <CloseCircleOutlined className="text-red-500 text-lg" />
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Pending Delegations */}
            {zmqQueue.pending_delegations > 0 && (
              <div className="mb-4 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800/40">
                <div className="flex items-center justify-between">
                  <Text className="text-sm">Pending Delegations</Text>
                  <Tag color="warning">{zmqQueue.pending_delegations}</Tag>
                </div>
              </div>
            )}

            {/* Sub Sockets Table */}
            <Text className="text-xs text-gray-500 dark:text-gray-400 mb-2 block">
              Subscribed Agents ({zmqQueue.sub_sockets.length})
            </Text>
            {zmqQueue.sub_sockets.length > 0 ? (
              <Table
                size="small"
                columns={subSocketColumns}
                dataSource={zmqQueue.sub_sockets}
                rowKey="agent_id"
                pagination={false}
                className="rounded-lg overflow-hidden"
              />
            ) : (
              <Text type="secondary" className="text-xs">No agents subscribed to ZeroMQ bus</Text>
            )}
          </>
        ) : (
          <Empty description="ZeroMQ Bus is not initialized" image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </div>
    </Card>
  );
}

export default function Queue() {
  const { currentBotId } = useAppStore();
  const queryClient = useQueryClient();

  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: api.listBots,
  });

  const activeBotId = currentBotId || bots?.find((b) => b.is_default)?.id || bots?.[0]?.id;

  // Subscribe to page:queue room when component mounts
  useEffect(() => {
    const ws = getWSRef()?.current;
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'subscribe', room: 'page:queue' }));
    }
  }, [activeBotId]);

  // Listen for queue_update WebSocket messages
  useQuery({
    queryKey: ['ws-queue-trigger'],
    queryFn: () => Promise.resolve(),
    enabled: false,
    staleTime: Infinity,
  });

  const botIds = activeBotId ? [activeBotId] : (bots?.map((b) => b.id) || []);

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            Message Queue Monitor
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Real-time view of Channel and Agent layer queues
          </p>
        </div>
        <Space>
          <SyncOutlined className="text-gray-400" />
          <Text type="secondary" className="text-xs">Live updates</Text>
        </Space>
      </div>

      {/* Bot selector if multiple bots */}
      {bots && bots.length > 1 && (
        <div className="mt-4 shrink-0">
          <Select
            value={activeBotId}
            onChange={(val) => queryClient.invalidateQueries({ queryKey: ['queue-status', val] })}
            options={bots.map((b) => ({ label: b.name, value: b.id }))}
            className="w-52"
          />
        </div>
      )}

      {/* Queue Cards */}
      <div className="flex-1 min-h-0 overflow-y-auto mt-4 space-y-4">
        {botIds.length === 0 ? (
          <Card className="rounded-xl">
            <Empty description="No bots available" />
          </Card>
        ) : (
          botIds.map((botId) => (
            <BotQueueCard key={botId} botId={botId} />
          ))
        )}
      </div>
    </div>
  );
}
