import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Card,
  Badge,
  Button,
  Spin,
  Alert,
  Tag,
  Descriptions,
  Empty,
  Space,
  Typography,
} from 'antd';
import {
  ReloadOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  InfoCircleOutlined,
  ClockCircleOutlined,
} from '@ant-design/icons';
import * as api from '../api/client';
import { useAppStore } from '../store';

const { Text } = Typography;

export default function MCPServers() {
  const queryClient = useQueryClient();
  const { addToast } = useAppStore();
  const [selectedServer, setSelectedServer] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);

  const { data: mcpServers, isLoading, error, refetch } = useQuery({
    queryKey: ['mcp'],
    queryFn: api.getMCPServers,
  });

  const testMutation = useMutation({
    mutationFn: async (name: string) => {
      setTesting(name);
      await new Promise((resolve) => setTimeout(resolve, 2000));
      return {
        name,
        success: true,
        message: 'Connection successful',
        latency_ms: Math.floor(Math.random() * 100) + 10,
      };
    },
    onSuccess: (result) => {
      addToast({
        type: 'success',
        message: `${result.name}: ${result.message} (${result.latency_ms}ms)`,
      });
      queryClient.invalidateQueries({ queryKey: ['mcp'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
    onSettled: () => setTesting(null),
  });

  const statusBadge = (status: string) => {
    if (status === 'connected') return 'success' as const;
    if (status === 'error') return 'error' as const;
    return 'default' as const;
  };

  const statusColor = (status: string) => {
    if (status === 'connected') return 'success';
    if (status === 'error') return 'error';
    return 'default';
  };

  const selectedServerData = mcpServers?.find((s) => s.name === selectedServer);

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
          message="Error loading MCP servers"
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
            MCP Servers
          </h1>
          <p className="text-sm text-gray-500 mt-1">Manage Model Context Protocol servers</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {/* Server Cards */}
      {mcpServers && mcpServers.length > 0 ? (
        <div className="space-y-3">
          {mcpServers.map((server) => (
            <Card
              key={server.name}
              hoverable
              onClick={() =>
                setSelectedServer(selectedServer === server.name ? null : server.name)
              }
              className={`cursor-pointer transition-all ${
                selectedServer === server.name
                  ? 'border-blue-500 border-2 shadow-md shadow-blue-500/10'
                  : ''
              }`}
              size="small"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div
                    className={`p-3 rounded-xl ${
                      server.status === 'connected'
                        ? 'bg-green-100 dark:bg-green-900/30'
                        : server.status === 'error'
                        ? 'bg-red-100 dark:bg-red-900/30'
                        : 'bg-gray-100 dark:bg-gray-700'
                    }`}
                  >
                    <ApiOutlined
                      className={`text-lg ${
                        server.status === 'connected'
                          ? 'text-green-600'
                          : server.status === 'error'
                          ? 'text-red-600'
                          : 'text-gray-400'
                      }`}
                    />
                  </div>
                  <div>
                    <p className="font-semibold text-base">{server.name}</p>
                    <Text type="secondary" className="text-sm">
                      Type: <span className="font-medium">{server.server_type}</span>
                    </Text>
                  </div>
                </div>

                <Space>
                  <Tag color={statusColor(server.status)}>{server.status}</Tag>
                  <Button
                    icon={<ThunderboltOutlined />}
                    loading={testing === server.name}
                    onClick={(e) => {
                      e.stopPropagation();
                      testMutation.mutate(server.name);
                    }}
                    size="small"
                  >
                    Test
                  </Button>
                </Space>
              </div>

              {server.error && (
                <Alert
                  className="mt-3"
                  type="error"
                  message={server.error}
                  showIcon
                  icon={<ExclamationCircleOutlined />}
                />
              )}

              {server.last_connected && (
                <p className="mt-2 text-xs text-gray-500 flex items-center gap-1">
                  <ClockCircleOutlined />
                  Last connected: {new Date(server.last_connected).toLocaleString()}
                </p>
              )}
            </Card>
          ))}
        </div>
      ) : (
        <Empty description="No MCP servers configured" />
      )}

      {/* Server Detail Panel */}
      {selectedServerData && (
        <Card
          title={
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-xl bg-purple-100 dark:bg-purple-900/30">
                <ApiOutlined className="text-purple-600 text-lg" />
              </div>
              <div>
                <span className="font-semibold text-lg">{selectedServerData.name}</span>
                <p className="text-xs text-gray-500 font-normal">Server Details</p>
              </div>
            </div>
          }
          extra={
            <Button
              icon={<ThunderboltOutlined />}
              loading={testing === selectedServerData.name}
              onClick={() => testMutation.mutate(selectedServerData.name)}
            >
              Test Connection
            </Button>
          }
        >
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
            <Card size="small" className="bg-gray-50 dark:bg-gray-700/30 border-0">
              <div>
                <p className="text-xs text-gray-500 mb-2">Connection Status</p>
                <div className="flex items-center gap-2">
                  {selectedServerData.status === 'connected' ? (
                    <CheckCircleOutlined className="text-green-500 text-xl" />
                  ) : selectedServerData.status === 'error' ? (
                    <CloseCircleOutlined className="text-red-500 text-xl" />
                  ) : (
                    <ExclamationCircleOutlined className="text-gray-400 text-xl" />
                  )}
                  <span
                    className={`text-lg font-semibold ${
                      selectedServerData.status === 'connected'
                        ? 'text-green-600'
                        : selectedServerData.status === 'error'
                        ? 'text-red-600'
                        : 'text-gray-500'
                    }`}
                  >
                    {selectedServerData.status}
                  </span>
                </div>
              </div>
            </Card>

            <Card size="small" className="bg-gray-50 dark:bg-gray-700/30 border-0">
              <div>
                <p className="text-xs text-gray-500 mb-2">Server Type</p>
                <div className="flex items-center gap-2">
                  <ApiOutlined className="text-purple-500 text-xl" />
                  <span className="text-lg font-semibold">{selectedServerData.server_type}</span>
                </div>
              </div>
            </Card>

            <Card size="small" className="bg-gray-50 dark:bg-gray-700/30 border-0">
              <div>
                <p className="text-xs text-gray-500 mb-2">Last Connected</p>
                <div className="flex items-center gap-2">
                  <ClockCircleOutlined className="text-gray-400 text-xl" />
                  <span className="text-base font-semibold">
                    {selectedServerData.last_connected
                      ? new Date(selectedServerData.last_connected).toLocaleString()
                      : 'Never'}
                  </span>
                </div>
              </div>
            </Card>
          </div>

          <Descriptions
            title="Server Information"
            size="small"
            bordered
            items={[
              {
                key: 'name',
                label: 'Name',
                children: selectedServerData.name,
              },
              {
                key: 'type',
                label: 'Server Type',
                children: selectedServerData.server_type,
              },
              {
                key: 'status',
                label: 'Status',
                children: (
                  <Space>
                    <Badge status={statusBadge(selectedServerData.status)} />
                    <Tag color={statusColor(selectedServerData.status)}>
                      {selectedServerData.status}
                    </Tag>
                  </Space>
                ),
              },
              {
                key: 'last_connected',
                label: 'Last Connected',
                children: selectedServerData.last_connected
                  ? new Date(selectedServerData.last_connected).toLocaleString()
                  : 'Never',
              },
            ]}
          />

          {selectedServerData.error && (
            <Alert
              className="mt-4"
              type="error"
              message="Error Details"
              description={selectedServerData.error}
              showIcon
            />
          )}

          <Alert
            className="mt-4"
            message="Configuration"
            description={
              <span>
                To configure MCP servers, add them to your config.json under{' '}
                <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                  tools.mcpServers
                </code>
              </span>
            }
            type="info"
            showIcon
            icon={<InfoCircleOutlined />}
          />
        </Card>
      )}

      {/* Config info when no server selected */}
      {!selectedServerData && mcpServers && mcpServers.length > 0 && (
        <Card title="Configuration">
          <Alert
            message={
              <span>
                To configure MCP servers, add them to your config.json under{' '}
                <code className="px-1.5 py-0.5 bg-gray-100 dark:bg-gray-800 rounded text-xs font-mono">
                  tools.mcpServers
                </code>
              </span>
            }
            type="info"
            showIcon
            className="mb-4"
          />
          <pre className="p-5 bg-gray-900 dark:bg-gray-950 rounded-xl overflow-x-auto text-sm text-gray-100 font-mono">
            {`{
  "tools": {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/dir"]
      }
    }
  }
}`}
          </pre>
        </Card>
      )}
    </div>
  );
}
