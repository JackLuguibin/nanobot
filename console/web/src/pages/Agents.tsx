import { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Button,
  Card,
  Modal,
  Input,
  Form,
  Select,
  Tag,
  Tooltip,
  Empty,
  Popconfirm,
  Spin,
  Space,
  Divider,
  Typography,
  Checkbox,
  Upload,
  Switch,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  ReloadOutlined,
  UploadOutlined,
  DownloadOutlined,
  EyeInvisibleOutlined,
} from '@ant-design/icons';
import { Bot, Radio } from 'lucide-react';
import { useAppStore } from '../store';
import * as api from '../api/client';
import type { Agent, AgentCreateRequest } from '../api/types_agents';

const { TextArea } = Input;

// 分类配置
const CATEGORIES = [
  { key: 'all', label: '全部', color: '#1890ff' },
  { key: 'general', label: '通用基础', color: '#52c41a' },
  { key: 'content', label: '内容创作', color: '#ff7875' },
  { key: 'office', label: '企业办公', color: '#faad14' },
];

// 根据agent名称或描述推断分类（简单实现）
function getAgentCategory(agent: Agent): string {
  const name = agent.name.toLowerCase();
  const desc = (agent.description || '').toLowerCase();
  const text = `${name} ${desc}`;
  
  if (text.includes('内容') || text.includes('创作') || text.includes('content') || text.includes('creator')) {
    return 'content';
  }
  if (text.includes('办公') || text.includes('企业') || text.includes('office') || text.includes('enterprise')) {
    return 'office';
  }
  return 'general';
}

export default function Agents() {
  const queryClient = useQueryClient();
  const { currentBotId, addToast } = useAppStore();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>('all');
  const [selectedAgents, setSelectedAgents] = useState<Set<string>>(new Set());
  const [importModalOpen, setImportModalOpen] = useState(false);
  const [formData, setFormData] = useState<AgentCreateRequest>({
    name: '',
    description: '',
    model: null,
    temperature: null,
    system_prompt: '',
    skills: [],
    topics: [],
    collaborators: [],
    enabled: true,
  });

  const { data: agents = [], isLoading, error, refetch } = useQuery({
    queryKey: ['agents', currentBotId],
    queryFn: () => api.listAgents(currentBotId!),
    enabled: !!currentBotId,
  });

  const { data: systemStatus } = useQuery({
    queryKey: ['agents-status', currentBotId],
    queryFn: () => api.getAgentsSystemStatus(currentBotId!),
    enabled: !!currentBotId,
  });

  const { data: botStatus } = useQuery({
    queryKey: ['status', currentBotId],
    queryFn: () => api.getStatus(currentBotId!),
    enabled: !!currentBotId,
  });

  const { data: skillsList } = useQuery({
    queryKey: ['skills', currentBotId],
    queryFn: () => api.listSkills(currentBotId),
    enabled: !!currentBotId,
  });

  // 根据分类筛选agents
  const filteredAgents = useMemo(() => {
    if (selectedCategory === 'all') return agents;
    return agents.filter((agent) => getAgentCategory(agent) === selectedCategory);
  }, [agents, selectedCategory]);

  const createMutation = useMutation({
    mutationFn: (data: AgentCreateRequest) => api.createAgent(currentBotId!, data),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: `Agent "${agent.name}" 创建成功` });
      setCreateModalOpen(false);
      resetForm();
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `创建失败: ${err.message}` });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: Partial<Agent> }) =>
      api.updateAgent(currentBotId!, agentId, data),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      addToast({ type: 'success', message: `Agent "${agent.name}" 更新成功` });
      setEditModalOpen(false);
      setSelectedAgent(null);
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `更新失败: ${err.message}` });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (agentId: string) => api.deleteAgent(currentBotId!, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: 'Agent 已删除' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `删除失败: ${err.message}` });
    },
  });

  const enableMutation = useMutation({
    mutationFn: (agentId: string) => api.enableAgent(currentBotId!, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: 'Agent 已启用' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `启用失败: ${err.message}` });
    },
  });

  const disableMutation = useMutation({
    mutationFn: (agentId: string) => api.disableAgent(currentBotId!, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: 'Agent 已禁用' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `禁用失败: ${err.message}` });
    },
  });

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      model: null,
      temperature: null,
      system_prompt: '',
      skills: [],
      topics: [],
      collaborators: [],
      enabled: true,
    });
  };

  const handleCreate = () => {
    if (formData.name.trim()) {
      createMutation.mutate(formData);
    }
  };

  const handleEdit = (agent: Agent) => {
    setSelectedAgent(agent);
    setFormData({
      name: agent.name,
      description: agent.description || '',
      model: agent.model,
      temperature: agent.temperature,
      system_prompt: agent.system_prompt || '',
      skills: agent.skills,
      topics: agent.topics,
      collaborators: agent.collaborators,
      enabled: agent.enabled,
    });
    setEditModalOpen(true);
  };

  const handleUpdate = () => {
    if (selectedAgent && formData.name.trim()) {
      updateMutation.mutate({ agentId: selectedAgent.id, data: formData });
    }
  };

  const handleExport = () => {
    const agentsToExport = selectedAgents.size > 0
      ? agents.filter((a) => selectedAgents.has(a.id))
      : agents;
    
    const dataStr = JSON.stringify(agentsToExport, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `agents-${new Date().toISOString().split('T')[0]}.json`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    addToast({ type: 'success', message: '导出成功' });
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const importedAgents = JSON.parse(text);
      
      if (!Array.isArray(importedAgents)) {
        throw new Error('无效的导入文件格式');
      }

      let successCount = 0;
      let errorCount = 0;

      for (const agentData of importedAgents) {
        try {
          await api.createAgent(currentBotId!, {
            name: agentData.name,
            description: agentData.description || null,
            model: agentData.model || null,
            temperature: agentData.temperature || null,
            system_prompt: agentData.system_prompt || null,
            skills: agentData.skills || [],
            topics: agentData.topics || [],
            collaborators: agentData.collaborators || [],
            enabled: agentData.enabled !== undefined ? agentData.enabled : true,
          });
          successCount++;
        } catch (err) {
          errorCount++;
          console.error('导入agent失败:', err);
        }
      }

      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      addToast({
        type: successCount > 0 ? 'success' : 'error',
        message: `导入完成: 成功 ${successCount} 个, 失败 ${errorCount} 个`,
      });
      setImportModalOpen(false);
    } catch (err) {
      addToast({ type: 'error', message: `导入失败: ${err instanceof Error ? err.message : '未知错误'}` });
    }
  };

  const handleToggleSelect = (agentId: string) => {
    setSelectedAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedAgents.size === filteredAgents.length) {
      setSelectedAgents(new Set());
    } else {
      setSelectedAgents(new Set(filteredAgents.map((a) => a.id)));
    }
  };

  if (!currentBotId) {
    return (
      <div className="p-6 flex flex-col flex-1 min-h-0">
        <Empty description="请先选择一个 Bot" className="py-20" />
      </div>
    );
  }

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Agent 管理
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 hidden sm:block">
            管理多个 AI Agent，每个 Agent 拥有独立的配置和能力
          </p>
        </div>
        <Space align="center" size="middle">
          {systemStatus && (
            <Tag 
              icon={<Radio className="w-3 h-3" />} 
              color={systemStatus.zmq_initialized ? 'success' : 'default'}
              className="!m-0"
            >
              ZeroMQ: {systemStatus.zmq_initialized ? '已连接' : '未连接'}
            </Tag>
          )}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            className="border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500"
          >
            <span className="hidden sm:inline">刷新</span>
          </Button>
          <Button
            icon={<UploadOutlined />}
            onClick={() => setImportModalOpen(true)}
            className="border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500"
          >
            <span className="hidden sm:inline">导入</span>
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
            className="shadow-md shadow-blue-500/25"
          >
            <span className="hidden sm:inline">创建 Agent</span>
          </Button>
        </Space>
      </div>

      {/* Category Filter */}
      <div className="flex items-center gap-2.5 mb-6 flex-wrap">
        {CATEGORIES.map((cat) => (
          <button
            key={cat.key}
            onClick={() => setSelectedCategory(cat.key)}
            className={`
              px-5 py-2 rounded-full text-sm font-medium transition-all duration-200
              ${
                selectedCategory === cat.key
                  ? 'bg-blue-500 text-white shadow-md shadow-blue-500/30'
                  : 'bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300 hover:border-gray-300 dark:hover:border-gray-600 hover:shadow-sm'
              }
            `}
          >
            {cat.label}
          </button>
        ))}
        <button
          className="px-5 py-2 rounded-full text-sm font-medium border border-dashed border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-all"
        >
          + 添加分类
        </button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-12 shrink-0">
          <Spin size="large" />
        </div>
      ) : error ? (
        <Empty description={`错误: ${(error as Error).message}`} className="py-12 shrink-0" />
      ) : filteredAgents.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <Empty
            description={
              <span className="text-gray-500 dark:text-gray-400">
                暂无 Agent，点击上方按钮创建
              </span>
            }
            className="py-12"
          />
        </div>
      ) : (
        <div className="w-full grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {filteredAgents.map((agent) => {
            const category = getAgentCategory(agent);
            const categoryConfig = CATEGORIES.find((c) => c.key === category) || CATEGORIES[0];
            const isSelected = selectedAgents.has(agent.id);
            
            return (
              <Card
                key={agent.id}
                className="rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm hover:shadow-lg transition-all duration-300 relative overflow-hidden group"
                styles={{ body: { padding: 0 } }}
                hoverable
              >
                {/* Accent bar — content starts below via padding-top */}
                <div
                  className="absolute top-0 left-0 right-0 h-1.5 z-[1]"
                  style={{ backgroundColor: categoryConfig.color }}
                />

                <div className="relative z-0 px-3.5 pb-3 pt-3.5">
                  {/* Header: checkbox + icon + title/tags (flow layout, no overlap) */}
                  <div className="flex items-start gap-2.5 mb-2">
                    <Checkbox
                      checked={isSelected}
                      onChange={() => handleToggleSelect(agent.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="mt-1 shrink-0"
                    />
                    <div
                      className="w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-transform group-hover:scale-105"
                      style={{ backgroundColor: `${categoryConfig.color}15` }}
                    >
                      <Bot className="w-[18px] h-[18px]" style={{ color: categoryConfig.color }} />
                    </div>
                    <div className="flex-1 min-w-0 space-y-1.5">
                      <h3 className="font-medium text-gray-900 dark:text-gray-100 text-sm leading-snug line-clamp-2 break-words">
                        {agent.name}
                      </h3>
                      <div className="flex flex-wrap items-center gap-1">
                        <Tag
                          className="text-xs !m-0 border-0 px-1.5 py-0.5 rounded-md leading-none"
                          style={{
                            backgroundColor: `${categoryConfig.color}20`,
                            color: categoryConfig.color,
                          }}
                        >
                          {categoryConfig.label}
                        </Tag>
                        {agent.enabled && (
                          <Tag
                            className="text-xs !m-0 border-0 px-1.5 py-0.5 rounded-md leading-none dark:!bg-[#2a1f4a] dark:!text-[#b37feb]"
                            style={{ backgroundColor: '#f0f0ff', color: '#722ed1' }}
                          >
                            系统
                          </Tag>
                        )}
                      </div>
                      {agent.description && (
                        <p className="text-xs text-gray-500 dark:text-gray-400 line-clamp-2 leading-snug pt-0.5">
                          {agent.description}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex items-center justify-end gap-0.5 pt-2.5 mt-0.5 border-t border-gray-100 dark:border-gray-700">
                    <Tooltip title="编辑">
                      <Button
                        type="text"
                        size="small"
                        icon={<EditOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEdit(agent);
                        }}
                        className="text-gray-500 dark:text-gray-400 hover:text-blue-500 dark:hover:text-blue-400 !px-1"
                      />
                    </Tooltip>
                    <Tooltip title="导出">
                      <Button
                        type="text"
                        size="small"
                        icon={<DownloadOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          const dataStr = JSON.stringify(agent, null, 2);
                          const dataBlob = new Blob([dataStr], { type: 'application/json' });
                          const url = URL.createObjectURL(dataBlob);
                          const link = document.createElement('a');
                          link.href = url;
                          link.download = `agent-${agent.id}.json`;
                          document.body.appendChild(link);
                          link.click();
                          document.body.removeChild(link);
                          URL.revokeObjectURL(url);
                          addToast({ type: 'success', message: '导出成功' });
                        }}
                        className="text-gray-500 dark:text-gray-400 hover:text-green-500 dark:hover:text-green-400 !px-1"
                      />
                    </Tooltip>
                    <Popconfirm
                      title="确认隐藏"
                      description="确定要隐藏这个 Agent 吗？"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        disableMutation.mutate(agent.id);
                      }}
                      okText="隐藏"
                      cancelText="取消"
                      okButtonProps={{ danger: true }}
                    >
                      <Tooltip title="隐藏">
                        <Button
                          type="text"
                          size="small"
                          icon={<EyeInvisibleOutlined />}
                          onClick={(e) => e.stopPropagation()}
                          className="text-gray-500 dark:text-gray-400 hover:text-orange-500 dark:hover:text-orange-400 !px-1"
                        />
                      </Tooltip>
                    </Popconfirm>
                  </div>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Batch Actions */}
      {selectedAgents.size > 0 && (
        <div className="fixed bottom-6 left-1/2 transform -translate-x-1/2 z-10">
          <Card className="shadow-xl border border-gray-200 dark:border-gray-700 rounded-xl">
            <Space size="middle">
              <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                已选择 <span className="text-blue-500 font-semibold">{selectedAgents.size}</span> 个 Agent
              </span>
              <Divider type="vertical" className="!my-0" />
              <Button size="small" onClick={handleSelectAll}>
                {selectedAgents.size === filteredAgents.length ? '取消全选' : '全选'}
              </Button>
              <Button size="small" icon={<DownloadOutlined />} onClick={handleExport}>
                批量导出
              </Button>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => {
                  Modal.confirm({
                    title: '确认删除',
                    content: `确定要删除选中的 ${selectedAgents.size} 个 Agent 吗？此操作不可恢复。`,
                    okText: '删除',
                    okType: 'danger',
                    cancelText: '取消',
                    onOk: () => {
                      selectedAgents.forEach((id) => {
                        deleteMutation.mutate(id);
                      });
                      setSelectedAgents(new Set());
                    },
                  });
                }}
              >
                批量删除
              </Button>
            </Space>
          </Card>
        </div>
      )}

      {/* Create Modal */}
      <Modal
        title="创建 Agent"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          resetForm();
        }}
        okText="创建"
        cancelText="取消"
        confirmLoading={createMutation.isPending}
        okButtonProps={{ disabled: !formData.name.trim() }}
        width={640}
        destroyOnClose
        styles={{ body: { maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form layout="vertical" className="pt-2">
          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide">
            基本信息
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Agent 名称" required>
            <Input
              placeholder="例如: 代码审查、文档编写、测试生成"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              onPressEnter={handleCreate}
            />
          </Form.Item>
          <Form.Item label="描述">
            <TextArea
              rows={2}
              placeholder="这个 Agent 的功能是什么？"
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value || null })}
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            模型配置
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="模型">
              <Select
                placeholder="选择模型（为空则使用默认）"
                value={formData.model || undefined}
                onChange={(v) => setFormData({ ...formData, model: v || null })}
                allowClear
                showSearch
                optionFilterProp="value"
                options={
                  (botStatus?.model ? [botStatus.model] : []).map((m) => ({
                    value: m,
                    label: m,
                  }))
                }
                className="w-full"
              />
            </Form.Item>
            <Form.Item label="Temperature">
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                placeholder="0.1 - 1.0"
                value={formData.temperature ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    temperature: e.target.value ? parseFloat(e.target.value) : null,
                  })
                }
              />
            </Form.Item>
          </div>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            系统提示词与技能
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="系统提示词">
            <TextArea
              rows={4}
              placeholder="定义 Agent 的行为和个性..."
              value={formData.system_prompt || ''}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value || null })}
            />
          </Form.Item>
          <Form.Item label="技能">
            <Select
              mode="multiple"
              placeholder="选择技能"
              value={formData.skills || []}
              onChange={(v) => setFormData({ ...formData, skills: v || [] })}
              options={
                (skillsList || []).map((s) => ({
                  value: s.name,
                  label: s.name,
                }))
              }
              optionRender={(option) => {
                const desc = (option.data as { description?: string })?.description;
                return (
                  <Space>
                    <span>{option.label}</span>
                    {desc && (
                      <Typography.Text type="secondary" className="text-xs">
                        - {desc}
                      </Typography.Text>
                    )}
                  </Space>
                );
              }}
              className="w-full"
            />
          </Form.Item>
          <Form.Item
            label="ZeroMQ Topics"
            extra="Agent 将订阅这些主题以进行 Agent 间通信"
          >
            <Select
              mode="tags"
              placeholder="添加主题（按 Enter）"
              value={formData.topics || []}
              onChange={(v) => setFormData({ ...formData, topics: v || [] })}
              tokenSeparators={[',']}
              className="w-full"
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Edit Modal */}
      <Modal
        title={`编辑 Agent: ${selectedAgent?.name ?? ''}`}
        open={editModalOpen}
        onOk={handleUpdate}
        onCancel={() => {
          setEditModalOpen(false);
          setSelectedAgent(null);
          resetForm();
        }}
        okText="保存"
        cancelText="取消"
        confirmLoading={updateMutation.isPending}
        okButtonProps={{ disabled: !formData.name.trim() }}
        width={640}
        destroyOnClose
        styles={{ body: { maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form layout="vertical" className="pt-2">
          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide">
            基本信息
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Agent 名称" required>
            <Input
              placeholder="例如: 代码审查、文档编写"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </Form.Item>
          <Form.Item label="描述">
            <TextArea
              rows={2}
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value || null })}
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            模型配置
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="模型">
              <Select
                placeholder="选择模型（为空则使用默认）"
                value={formData.model || undefined}
                onChange={(v) => setFormData({ ...formData, model: v || null })}
                allowClear
                showSearch
                optionFilterProp="value"
                options={
                  (botStatus?.model ? [botStatus.model] : []).map((m) => ({
                    value: m,
                    label: m,
                  }))
                }
                className="w-full"
              />
            </Form.Item>
            <Form.Item label="Temperature">
              <Input
                type="number"
                step="0.1"
                min="0"
                max="2"
                placeholder="0.1 - 1.0"
                value={formData.temperature ?? ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    temperature: e.target.value ? parseFloat(e.target.value) : null,
                  })
                }
              />
            </Form.Item>
          </div>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            系统提示词与技能
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="系统提示词">
            <TextArea
              rows={4}
              value={formData.system_prompt || ''}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value || null })}
            />
          </Form.Item>
          <Form.Item label="技能">
            <Select
              mode="multiple"
              placeholder="选择技能"
              value={formData.skills || []}
              onChange={(v) => setFormData({ ...formData, skills: v || [] })}
              options={
                (skillsList || []).map((s) => ({
                  value: s.name,
                  label: s.name,
                }))
              }
              optionRender={(option) => {
                const desc = (option.data as { description?: string })?.description;
                return (
                  <Space>
                    <span>{option.label}</span>
                    {desc && (
                      <Typography.Text type="secondary" className="text-xs">
                        - {desc}
                      </Typography.Text>
                    )}
                  </Space>
                );
              }}
              className="w-full"
            />
          </Form.Item>
          <Form.Item
            label="ZeroMQ Topics"
            extra="Agent 将订阅这些主题以进行 Agent 间通信"
          >
            <Select
              mode="tags"
              placeholder="添加主题（按 Enter）"
              value={formData.topics || []}
              onChange={(v) => setFormData({ ...formData, topics: v || [] })}
              tokenSeparators={[',']}
              className="w-full"
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            状态
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="启用">
            <Switch
              checked={formData.enabled}
              onChange={(checked) => setFormData({ ...formData, enabled: checked })}
            />
          </Form.Item>
        </Form>
      </Modal>

      {/* Import Modal */}
      <Modal
        title="导入 Agent"
        open={importModalOpen}
        onCancel={() => setImportModalOpen(false)}
        footer={null}
        width={500}
      >
        <div className="py-4">
          <Upload.Dragger
            accept=".json"
            beforeUpload={(file) => {
              handleImport(file);
              return false;
            }}
            showUploadList={false}
          >
            <p className="ant-upload-drag-icon">
              <UploadOutlined className="text-4xl text-gray-400" />
            </p>
            <p className="ant-upload-text">点击或拖拽文件到此区域上传</p>
            <p className="ant-upload-hint">支持 JSON 格式的 Agent 配置文件</p>
          </Upload.Dragger>
        </div>
      </Modal>
    </div>
  );
}
