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
  Typography,
  Modal,
} from 'antd';
import {
  ReloadOutlined,
  PoweroffOutlined,
  SyncOutlined,
  ClockCircleOutlined,
  TeamOutlined,
  MessageOutlined,
  DollarOutlined,
  ThunderboltOutlined,
  BarChartOutlined,
} from '@ant-design/icons';
import { Column, Tiny, Pie } from '@ant-design/plots';
import type { UsageHistoryItem } from '../api/types';
import { formatTokenCount, formatCost } from '../utils/format';

const { Text } = Typography;

/** 将 usageHistory 转为柱状图分组数据 */
function toColumnData(history: UsageHistoryItem[]) {
  return history.flatMap((d) => [
    { date: d.date, type: '输入', value: d.prompt_tokens ?? 0 },
    { date: d.date, type: '输出', value: d.completion_tokens ?? 0 },
  ]);
}

function formatUptime(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export default function Dashboard() {
  const queryClient = useQueryClient();
  const { setStatus, setChannels, setMCPServers, status, addToast, currentBotId } = useAppStore();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['status', currentBotId],
    queryFn: () => api.getStatus(currentBotId),
    refetchInterval: false,
  });

  const { data: bots = [] } = useQuery({
    queryKey: ['bots'],
    queryFn: api.listBots,
  });

  const { data: usageHistory, isLoading: usageLoading } = useQuery({
    queryKey: ['usage-history', currentBotId],
    queryFn: () => api.getUsageHistory(currentBotId, 14),
    refetchInterval: false,
  });

  // 用当前 bot 的 API 数据作为展示源，避免与 store 中其他 bot 或旧数据混用
  const displayStatus = data ?? status;

  useEffect(() => {
    if (data) {
      setStatus(data);
      setChannels(data.channels || []);
      setMCPServers(data.mcp_servers || []);
    }
  }, [data, setStatus, setChannels, setMCPServers]);

  const stopMutation = useMutation({
    mutationFn: () => {
      const botId =
        currentBotId || bots.find((b) => b.is_default)?.id || bots[0]?.id;
      if (!botId) {
        return Promise.reject(new Error('无法确定当前 Bot，请先在侧栏选择 Bot'));
      }
      return api.stopBot(botId);
    },
    onSuccess: () => {
      addToast({ type: 'success', message: 'Bot 已停止' });
      queryClient.invalidateQueries({ queryKey: ['status'] });
      queryClient.invalidateQueries({ queryKey: ['bots'] });
      queryClient.invalidateQueries({ queryKey: ['usage-history', currentBotId] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const restartMutation = useMutation({
    mutationFn: async () => {
      const botId =
        currentBotId || bots.find((b) => b.is_default)?.id || bots[0]?.id;
      if (!botId) {
        return Promise.reject(new Error('无法确定当前 Bot，请先在侧栏选择 Bot'));
      }
      await api.stopBot(botId);
      await api.startBot(botId);
    },
    onSuccess: () => {
      addToast({ type: 'success', message: 'Bot 重启成功' });
      queryClient.invalidateQueries({ queryKey: ['status'] });
      queryClient.invalidateQueries({ queryKey: ['bots'] });
      queryClient.invalidateQueries({ queryKey: ['usage-history', currentBotId] });
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
          {displayStatus?.running && (
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
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              refetch();
              queryClient.invalidateQueries({ queryKey: ['usage-history', currentBotId] });
            }}
          />
        </Space>
      </div>

      {/* Stat Cards：统一高度与数值区对齐；小屏 2 列、中屏 3 列、大屏 6 列，避免窄屏横向溢出 */}
      <div
        className="grid grid-cols-2 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3 sm:gap-4 min-w-0 [&_.ant-statistic-title]:min-h-[20px] [&_.ant-statistic-title]:text-xs [&_.ant-statistic-content]:min-h-[40px] [&_.ant-statistic-content]:flex [&_.ant-statistic-content]:items-end [&_.ant-statistic-content-value]:text-lg [&_.ant-statistic-content-value]:xl:text-2xl"
      >
        <Card hoverable className="h-full min-w-0 [&_.ant-card-body]:flex [&_.ant-card-body]:flex-col [&_.ant-card-body]:h-full [&_.ant-card-body]:min-w-0">
          <Statistic
            title="Status"
            value={displayStatus?.running ? 'Running' : 'Stopped'}
            styles={{ content: { color: displayStatus?.running ? '#16a34a' : '#9ca3af' } }}
            prefix={
              displayStatus?.running ? (
                <Badge status="processing" color="#22c55e" />
              ) : (
                <Badge status="default" />
              )
            }
          />
        </Card>
        <Card hoverable className="h-full min-w-0 [&_.ant-card-body]:flex [&_.ant-card-body]:flex-col [&_.ant-card-body]:h-full [&_.ant-card-body]:min-w-0">
          <Statistic
            title="Uptime"
            value={displayStatus?.running && displayStatus?.uptime_seconds ? formatUptime(displayStatus.uptime_seconds) : '-'}
            prefix={<ClockCircleOutlined className="text-blue-500" />}
          />
        </Card>
        <Card hoverable className="h-full min-w-0 [&_.ant-card-body]:flex [&_.ant-card-body]:flex-col [&_.ant-card-body]:h-full [&_.ant-card-body]:min-w-0">
          <Statistic
            title="Active Sessions"
            value={displayStatus?.active_sessions ?? 0}
            prefix={<TeamOutlined className="text-purple-500" />}
          />
        </Card>
        <Card hoverable className="h-full min-w-0 [&_.ant-card-body]:flex [&_.ant-card-body]:flex-col [&_.ant-card-body]:h-full [&_.ant-card-body]:min-w-0">
          <Statistic
            title="Messages Today"
            value={displayStatus?.messages_today ?? 0}
            prefix={<MessageOutlined className="text-orange-500" />}
          />
        </Card>
        <Card hoverable className="h-full min-w-0 [&_.ant-card-body]:flex [&_.ant-card-body]:flex-col [&_.ant-card-body]:h-full [&_.ant-card-body]:min-w-0">
          <Statistic
            title="Tokens Today"
            value={
              displayStatus?.token_usage?.total_tokens != null
                ? formatTokenCount(displayStatus.token_usage.total_tokens)
                : '-'
            }
            prefix={<ThunderboltOutlined className="text-amber-500" />}
          />
        </Card>
        <Card hoverable className="h-full min-w-0 [&_.ant-card-body]:flex [&_.ant-card-body]:flex-col [&_.ant-card-body]:h-full [&_.ant-card-body]:min-w-0">
          <Statistic
            title="Cost Today"
            value={
              displayStatus?.token_usage?.cost_usd != null && displayStatus.token_usage.cost_usd > 0
                ? formatCost(displayStatus.token_usage.cost_usd)
                : '-'
            }
            prefix={<DollarOutlined className="text-green-500" />}
          />
        </Card>
      </div>

      {/* Model Info & Token Usage */}
      {displayStatus?.model && (
        <Card size="small">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-blue-100 dark:bg-blue-900/30">
                <ThunderboltOutlined className="text-blue-600 text-lg" />
              </div>
              <div>
                <Text type="secondary" className="text-xs">
                  Current Model
                </Text>
                <p className="font-semibold text-base">{displayStatus.model}</p>
              </div>
            </div>
            {displayStatus?.token_usage && ((displayStatus?.token_usage?.total_tokens ?? 0) + (displayStatus?.token_usage?.prompt_tokens ?? 0) + (displayStatus?.token_usage?.completion_tokens ?? 0)) > 0 && (
              <div className="flex flex-col gap-2 text-sm">
                <div className="flex items-center gap-4">
                  <div>
                    <Text type="secondary" className="text-xs block">今日 Token 使用</Text>
                    <span className="font-medium">
                      {formatTokenCount(displayStatus?.token_usage?.total_tokens ?? 0)}
                    </span>
                    <Text type="secondary" className="text-xs ml-1">total</Text>
                  </div>
                  <div>
                    <Text type="secondary" className="text-xs block">输入</Text>
                    <span className="font-medium">
                      {formatTokenCount(displayStatus?.token_usage?.prompt_tokens ?? 0)}
                    </span>
                  </div>
                  <div>
                    <Text type="secondary" className="text-xs block">输出</Text>
                    <span className="font-medium">
                      {formatTokenCount(displayStatus?.token_usage?.completion_tokens ?? 0)}
                    </span>
                  </div>
                </div>
                {displayStatus?.token_usage?.by_model && Object.keys(displayStatus.token_usage.by_model).length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(displayStatus.token_usage.by_model).map(([model, u]) => (
                      <Tag key={model} className="m-0">
                        {model}: {formatTokenCount(u.total_tokens ?? 0)}
                        {displayStatus?.token_usage?.cost_by_model?.[model] != null &&
                          displayStatus.token_usage.cost_by_model[model] > 0 && (
                            <span className="ml-1 text-green-600 dark:text-green-400">
                              ({formatCost(displayStatus.token_usage.cost_by_model[model])})
                            </span>
                          )}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>
            )}
            {/* 每日 Token 用量趋势图 */}
            {usageHistory && usageHistory.length > 0 && (
              <div className="w-full min-w-[320px]" style={{ maxWidth: 480 }}>
                <Text type="secondary" className="text-xs block mb-1">每日 Token 用量</Text>
                <div style={{ height: 44 }}>
                  <Tiny.Area
                    data={usageHistory.map((d) => ({
                      date: d.date.slice(5),
                      value: d.total_tokens ?? 0,
                    }))}
                    xField="date"
                    yField="value"
                    smooth
                    color="#3b82f6"
                    areaStyle={{ fill: 'l(90) 0:rgba(59,130,246,0.35) 1:rgba(59,130,246,0.05)' }}
                  />
                </div>
              </div>
            )}
          </div>
        </Card>
      )}

      {/* 每日 Token 使用量 + 按模型成本分布：水平并排 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card
          title={
            <span className="flex items-center gap-2">
              <BarChartOutlined className="text-amber-500" /> 每日 Token 使用量
            </span>
          }
          size="small"
        >
          {usageLoading ? (
            <div className="flex items-center justify-center h-[280px]">
              <Spin />
            </div>
          ) : usageHistory && usageHistory.length > 0 ? (
            <div className="h-[280px] w-full" style={{ minHeight: 240 }}>
              <Column
                data={toColumnData(usageHistory)}
                xField="date"
                yField="value"
                seriesField="type"
                group
                paddingBottom={56}
                scale={{
                  x: { padding: 0.5 },
                }}
                style={{
                  fill: (d: { type: string }) =>
                    d.type === '输入' ? '#3b82f6' : d.type === '输出' ? '#22c55e' : '#94a3b8',
                }}
                label={{
                  text: 'value',
                  position: 'top',
                  style: { dy: -16 },
                  formatter: (v: unknown) => {
                    const n = Number(v);
                    return n > 0 ? formatTokenCount(n) : '';
                  },
                }}
                axis={{
                  x: {
                    label: {
                      formatter: (v: string) => (typeof v === 'string' ? v.slice(5) : String(v)),
                    },
                    labelTextAlign: 'center',
                    labelTextBaseline: 'middle',
                    labelTransform: 'rotate(-30deg)',
                    labelSpacing: 12,
                  },
                  y: {
                    label: {
                      formatter: (v: string) => formatTokenCount(Number(v)),
                    },
                  },
                }}
                legend={{ position: 'top' }}
              />
            </div>
          ) : (
            <Text type="secondary" className="block text-center py-12">
              暂无使用数据，与模型对话后会自动记录
            </Text>
          )}
        </Card>

        <Card
          title={
            <span className="flex items-center gap-2">
              <ThunderboltOutlined className="text-amber-500" /> 按模型消耗占比
            </span>
          }
          size="small"
        >
          <div className="flex flex-col items-center gap-4 w-full">
            <div style={{ width: 180, height: 180 }}>
              <Pie
                data={Object.entries(displayStatus?.token_usage?.by_model ?? {})
                  .filter(([, v]) => (v.total_tokens ?? 0) > 0)
                  .map(([model, u]) => ({ type: model, value: u.total_tokens ?? 0 }))}
                angleField="value"
                colorField="type"
                radius={0.8}
                innerRadius={0.4}
                label={false}
                legend={false}
                tooltip={{
                  items: [
                    {
                      channel: 'y',
                      valueFormatter: (v: number) => formatTokenCount(v),
                    },
                  ],
                }}
              />
            </div>
            <div className="flex flex-col gap-2">
              {Object.entries(displayStatus?.token_usage?.by_model ?? {})
                .filter(([, v]) => (v.total_tokens ?? 0) > 0)
                .map(([model, u]) => (
                  <div key={model} className="flex items-center justify-between gap-4">
                    <span className="font-medium truncate max-w-[100px]">{model}</span>
                    <span className="text-amber-600 dark:text-amber-400 font-mono">
                      {formatTokenCount(u.total_tokens ?? 0)}
                    </span>
                  </div>
                ))}
              {(!(displayStatus?.token_usage?.by_model) ||
                Object.entries(displayStatus?.token_usage?.by_model ?? {}).filter(([, u]) => (u.total_tokens ?? 0) > 0).length === 0) && (
                <Text type="secondary" className="text-xs">暂无数据</Text>
              )}
            </div>
          </div>
        </Card>
      </div>

    </div>
  );
}
