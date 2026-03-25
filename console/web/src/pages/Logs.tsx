import { useLayoutEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Table,
  Select,
  Input,
  Button,
  Tag,
  Statistic,
  Card,
  Space,
  Segmented,
  Tooltip,
  Typography,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  ReloadOutlined,
  CopyOutlined,
  CheckOutlined,
  CodeOutlined,
} from '@ant-design/icons';
import { useAppStore } from '../store';
import * as api from '../api/client';
import type { ToolCallLog } from '../api/types';

const { Text } = Typography;

export default function Logs() {
  const { addToast, currentBotId } = useAppStore();
  const [toolFilter, setToolFilter] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [searchQuery, setSearchQuery] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [limit, setLimit] = useState(100);
  const tableAreaRef = useRef<HTMLDivElement>(null);
  const [tableScrollY, setTableScrollY] = useState(320);

  useLayoutEffect(() => {
    const el = tableAreaRef.current;
    if (!el) return;
    const measure = () => {
      const h = el.getBoundingClientRect().height;
      // Ant Design table: header + horizontal scroll + pagination (~110px)
      setTableScrollY(Math.max(160, Math.floor(h - 110)));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const { data: logs, isLoading, error, refetch } = useQuery({
    queryKey: ['tool-logs', toolFilter, statusFilter, limit, currentBotId],
    queryFn: () => api.getToolLogs(limit, toolFilter || undefined, currentBotId),
    refetchInterval: false,
  });

  const filteredLogs = logs?.filter((log) => {
    if (statusFilter && log.status !== statusFilter) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        log.tool_name.toLowerCase().includes(q) ||
        JSON.stringify(log.arguments).toLowerCase().includes(q) ||
        (log.result?.toLowerCase().includes(q) ?? false)
      );
    }
    return true;
  });

  const formatDuration = (ms: number) => {
    if (ms < 1000) return `${ms}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
  };

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleTimeString();
  };

  const formatFullDate = (dateStr?: string) => {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleString();
  };

  const copyToClipboard = async (text: string, id: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch {
      addToast({ type: 'error', message: 'Failed to copy' });
    }
  };

  const uniqueTools = [...new Set(logs?.map((log) => log.tool_name) || [])];

  const successCount = filteredLogs?.filter((l) => l.status === 'success').length ?? 0;
  const errorCount = filteredLogs?.filter((l) => l.status === 'error').length ?? 0;
  const avgDuration =
    filteredLogs && filteredLogs.length > 0
      ? Math.round(
          filteredLogs.reduce((sum, l) => sum + l.duration_ms, 0) / filteredLogs.length
        )
      : 0;

  const columns: ColumnsType<ToolCallLog> = [
    {
      title: 'Status',
      key: 'status',
      width: 100,
      render: (_, log) => (
        <Tag color={log.status === 'success' ? 'success' : 'error'}>{log.status}</Tag>
      ),
    },
    {
      title: 'Tool',
      dataIndex: 'tool_name',
      key: 'tool_name',
      render: (name: string) => (
        <span className="font-mono font-medium flex items-center gap-1.5">
          <CodeOutlined className="text-gray-400" />
          {name}
        </span>
      ),
    },
    {
      title: 'Arguments',
      key: 'arguments',
      render: (_, log) => {
        const argStr = JSON.stringify(log.arguments);
        return (
          <Text
            type="secondary"
            className="font-mono text-xs"
            style={{ maxWidth: 300, display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
          >
            {argStr.slice(0, 80)}
            {argStr.length > 80 && '…'}
          </Text>
        );
      },
    },
    {
      title: 'Time',
      dataIndex: 'timestamp',
      key: 'timestamp',
      width: 110,
      render: (ts: string) => (
        <Tooltip title={formatFullDate(ts)}>
          <span className="text-gray-500 text-xs">{formatDate(ts)}</span>
        </Tooltip>
      ),
    },
    {
      title: 'Duration',
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 100,
      render: (ms: number) => (
        <span className={ms > 5000 ? 'text-amber-500 font-medium' : 'text-gray-500'}>
          {formatDuration(ms)}
        </span>
      ),
      sorter: (a, b) => a.duration_ms - b.duration_ms,
    },
  ];

  const expandedRowRender = (log: ToolCallLog) => (
    <div className="space-y-4 py-2 px-4">
      <div>
        <div className="flex items-center justify-between mb-2">
          <Text type="secondary" className="text-xs font-medium">
            Arguments
          </Text>
          <Button
            size="small"
            type="text"
            icon={
              copiedId === `args-${log.id}` ? (
                <CheckOutlined className="text-green-500" />
              ) : (
                <CopyOutlined />
              )
            }
            onClick={() =>
              copyToClipboard(JSON.stringify(log.arguments, null, 2), `args-${log.id}`)
            }
          />
        </div>
        <pre className="p-3 bg-gray-900 dark:bg-gray-950 rounded-xl text-xs text-gray-100 font-mono overflow-x-auto max-h-48">
          {JSON.stringify(log.arguments, null, 2)}
        </pre>
      </div>

      {log.result && (
        <div>
          <div className="flex items-center justify-between mb-2">
            <Text type="secondary" className="text-xs font-medium">
              Result
            </Text>
            <Button
              size="small"
              type="text"
              icon={
                copiedId === `result-${log.id}` ? (
                  <CheckOutlined className="text-green-500" />
                ) : (
                  <CopyOutlined />
                )
              }
              onClick={() => copyToClipboard(log.result!, `result-${log.id}`)}
            />
          </div>
          <pre className="p-3 bg-gray-900 dark:bg-gray-950 rounded-xl text-xs text-gray-100 font-mono overflow-x-auto max-h-64 whitespace-pre-wrap break-all">
            {log.result}
          </pre>
        </div>
      )}
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-1 flex-col p-6 space-y-6">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            Tool Logs
          </h1>
          <p className="text-sm text-gray-500 mt-1">View tool execution history</p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()}>
          Refresh
        </Button>
      </div>

      {/* Stats */}
      {filteredLogs && filteredLogs.length > 0 && (
        <div className="grid shrink-0 grid-cols-3 gap-4">
          <Card size="small">
            <Statistic title="Total Calls" value={filteredLogs.length} />
          </Card>
          <Card size="small">
            <Statistic
              title="Success Rate"
              value={
                filteredLogs.length > 0
                  ? Math.round((successCount / filteredLogs.length) * 100)
                  : 0
              }
              suffix="%"
              styles={{ content: { color: '#16a34a' } }}
            />
          </Card>
          <Card size="small">
            <Statistic title="Avg Duration" value={formatDuration(avgDuration)} />
          </Card>
        </div>
      )}

      {/* Filters */}
      <Space wrap className="shrink-0">
        <Input.Search
          placeholder="Search logs..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          onSearch={setSearchQuery}
          allowClear
          style={{ width: 240 }}
        />

        <Select
          value={toolFilter || undefined}
          placeholder="All Tools"
          allowClear
          onChange={(val) => setToolFilter(val || '')}
          style={{ width: 180 }}
          options={[
            ...uniqueTools.map((tool) => ({ value: tool, label: tool })),
          ]}
        />

        <Segmented
          className="activity-seg-align"
          value={statusFilter || 'all'}
          onChange={(val) => setStatusFilter(val === 'all' ? '' : String(val))}
          options={[
            { value: 'all', label: 'All' },
            {
              value: 'success',
              label: (
                <span className="text-green-600">
                  Success ({successCount})
                </span>
              ),
            },
            {
              value: 'error',
              label: (
                <span className="text-red-600">
                  Error ({errorCount})
                </span>
              ),
            },
          ]}
        />

        <Select
          value={limit}
          onChange={setLimit}
          style={{ width: 120 }}
          options={[
            { value: 50, label: 'Last 50' },
            { value: 100, label: 'Last 100' },
            { value: 200, label: 'Last 200' },
            { value: 500, label: 'Last 500' },
          ]}
        />
      </Space>

      {/* Table — 见 index.css `.logs-page-table-host`（scroll.y 只设 max-height，空表需 min-height 撑满） */}
      <div
        ref={tableAreaRef}
        className="logs-page-table-host min-h-0 min-w-0 flex flex-1 flex-col"
        style={{ ['--logs-table-body-y' as string]: `${tableScrollY}px` }}
      >
        <Table<ToolCallLog>
          dataSource={filteredLogs}
          columns={columns}
          rowKey="id"
          loading={isLoading}
          scroll={{ y: tableScrollY }}
          expandable={{
            expandedRowRender,
            expandRowByClick: true,
          }}
          locale={{
            emptyText: error ? (
              <div className="text-red-500">Error loading logs: {String(error)}</div>
            ) : (
              <Space direction="vertical" className="py-6">
                <CodeOutlined className="text-4xl text-gray-300" />
                <span>No tool logs found</span>
                {(toolFilter || statusFilter || searchQuery) && (
                  <Button
                    type="link"
                    size="small"
                    onClick={() => {
                      setToolFilter('');
                      setStatusFilter('');
                      setSearchQuery('');
                    }}
                  >
                    Clear filters
                  </Button>
                )}
              </Space>
            ),
          }}
          pagination={{ pageSize: 20, showSizeChanger: true, showTotal: (total) => `${total} logs` }}
          size="middle"
        />
      </div>
    </div>
  );
}
