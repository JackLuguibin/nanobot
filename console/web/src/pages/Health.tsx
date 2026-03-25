import { useQuery } from '@tanstack/react-query';
import {
  Card,
  Tag,
  Spin,
  Alert,
  Button,
  Typography,
  Empty,
} from 'antd';
import { ReloadOutlined, CheckCircleOutlined, ExclamationCircleOutlined, InfoCircleOutlined } from '@ant-design/icons';
import * as api from '../api/client';
import { useAppStore } from '../store';
import type { HealthIssue } from '../api/types';

const { Text } = Typography;

function IssueIcon({ severity }: { severity: string }) {
  if (severity === 'critical') return <ExclamationCircleOutlined className="text-red-500" />;
  if (severity === 'warning') return <ExclamationCircleOutlined className="text-amber-500" />;
  return <InfoCircleOutlined className="text-blue-500" />;
}

export default function Health() {
  const { currentBotId } = useAppStore();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['health-audit', currentBotId],
    queryFn: () => api.getHealthAudit(currentBotId),
  });

  const issues = data?.issues ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[320px]">
        <Spin size="large" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <Alert type="error" message="加载失败" description={String(error)} showIcon />
      </div>
    );
  }

  const criticalCount = issues.filter((i) => i.severity === 'critical').length;
  const warningCount = issues.filter((i) => i.severity === 'warning').length;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            健康检查
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            检查 Bootstrap 文件、MCP 配置、通道等
          </p>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => refetch()} />
      </div>

      {issues.length === 0 ? (
        <Card>
          <Empty
            image={<CheckCircleOutlined style={{ fontSize: 64, color: '#22c55e' }} />}
            description="未发现任何问题"
            className="py-12"
          />
        </Card>
      ) : (
        <>
          <Card size="small">
            <div className="flex items-center gap-4">
              {criticalCount > 0 && (
                <Tag color="red">严重 {criticalCount}</Tag>
              )}
              {warningCount > 0 && (
                <Tag color="orange">警告 {warningCount}</Tag>
              )}
              {issues.length - criticalCount - warningCount > 0 && (
                <Tag color="blue">提示 {issues.length - criticalCount - warningCount}</Tag>
              )}
            </div>
          </Card>

          <Card
            title="检查结果"
            size="small"
          >
            <div className="divide-y divide-gray-100 dark:divide-gray-700">
              {issues.map((issue: HealthIssue) => (
                <div key={issue.path ?? issue.message} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
                  <IssueIcon severity={issue.severity} />
                  <div className="flex-1 min-w-0">
                    <p className="font-medium">{issue.message}</p>
                    {issue.path && (
                      <Text type="secondary" className="text-xs">
                        {issue.path}
                      </Text>
                    )}
                  </div>
                  <Tag
                    color={
                      issue.severity === 'critical'
                        ? 'red'
                        : issue.severity === 'warning'
                        ? 'orange'
                        : 'blue'
                    }
                  >
                    {issue.severity === 'critical' ? '严重' : issue.severity === 'warning' ? '警告' : '提示'}
                  </Tag>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
