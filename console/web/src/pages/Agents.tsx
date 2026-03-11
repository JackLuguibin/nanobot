import { useState } from 'react';
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
  Switch,
  Space,
  Divider,
  Typography,
} from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
  BellOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import { Bot, Radio } from 'lucide-react';
import { useAppStore } from '../store';
import * as api from '../api/client';
import type { Agent, AgentCreateRequest } from '../api/types_agents';

const { TextArea } = Input;

export default function Agents() {
  const queryClient = useQueryClient();
  const { currentBotId, addToast } = useAppStore();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
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

  const { data: agents = [], isLoading, error } = useQuery({
    queryKey: ['agents', currentBotId],
    queryFn: () => api.listAgents(currentBotId!),
    enabled: !!currentBotId,
  });

  const { data: systemStatus } = useQuery({
    queryKey: ['agents-status', currentBotId],
    queryFn: () => api.getAgentsSystemStatus(currentBotId!),
    enabled: !!currentBotId,
  });

  // 获取 Bot 状态（包含默认模型）
  const { data: botStatus } = useQuery({
    queryKey: ['status', currentBotId],
    queryFn: () => api.getStatus(currentBotId!),
    enabled: !!currentBotId,
  });

  // 获取技能列表（复用现有 API）
  const { data: skillsList } = useQuery({
    queryKey: ['skills', currentBotId],
    queryFn: () => api.listSkills(currentBotId),
    enabled: !!currentBotId,
  });

  const createMutation = useMutation({
    mutationFn: (data: AgentCreateRequest) => api.createAgent(currentBotId!, data),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: `Agent "${agent.name}" created successfully` });
      setCreateModalOpen(false);
      resetForm();
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Create failed: ${err.message}` });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ agentId, data }: { agentId: string; data: Partial<Agent> }) =>
      api.updateAgent(currentBotId!, agentId, data),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      addToast({ type: 'success', message: `Agent "${agent.name}" updated` });
      setEditModalOpen(false);
      setSelectedAgent(null);
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Update failed: ${err.message}` });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (agentId: string) => api.deleteAgent(currentBotId!, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: 'Agent deleted' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Delete failed: ${err.message}` });
    },
  });

  const enableMutation = useMutation({
    mutationFn: (agentId: string) => api.enableAgent(currentBotId!, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: 'Agent enabled' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Enable failed: ${err.message}` });
    },
  });

  const disableMutation = useMutation({
    mutationFn: (agentId: string) => api.disableAgent(currentBotId!, agentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: 'Agent disabled' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Disable failed: ${err.message}` });
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

  if (!currentBotId) {
    return (
      <div className="p-6 flex flex-col flex-1 min-h-0">
        <Empty description="Please select a Bot first" className="py-20" />
      </div>
    );
  }

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between shrink-0 mb-6">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            Agent Management
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Manage multiple AI agents within this Bot
          </p>
        </div>
        <Space align="center">
          {systemStatus && (
            <Tag icon={<Radio className="w-3 h-3" />} color={systemStatus.zmq_initialized ? 'success' : 'default'}>
              ZeroMQ: {systemStatus.zmq_initialized ? 'Connected' : 'Disconnected'}
            </Tag>
          )}
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModalOpen(true)}
          >
            New Agent
          </Button>
        </Space>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-16 shrink-0">
          <Spin size="large" />
        </div>
      ) : error ? (
        <Empty description={`Error: ${(error as Error).message}`} className="py-16" />
      ) : agents.length === 0 ? (
        <Card
          className="rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm max-w-2xl mx-auto"
          styles={{ body: { padding: '3rem 2rem' } }}
        >
          <Empty
            description="No Agent yet, click the button above to create"
            className="py-8"
          >
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateModalOpen(true)}
              className="mt-2"
            >
              New Agent
            </Button>
          </Empty>
        </Card>
      ) : (
        <div className="max-w-5xl mx-auto w-full grid gap-5 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent) => (
            <Card
              key={agent.id}
              className="rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm hover:shadow-md transition-all duration-200"
              styles={{ body: { padding: '1.25rem 1.5rem' } }}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-3 min-w-0 flex-1">
                  <div className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center ${
                    agent.enabled
                      ? 'bg-blue-100 dark:bg-blue-900/40'
                      : 'bg-gray-100 dark:bg-gray-800'
                  }`}>
                    <Bot className={`w-5 h-5 ${
                      agent.enabled ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'
                    }`} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-gray-100 truncate">
                      {agent.name}
                    </h3>
                    <div className="flex items-center gap-1.5 mt-1">
                      <Tag
                        color={agent.enabled ? 'success' : 'default'}
                        className="text-xs !mr-0"
                      >
                        {agent.enabled ? 'Enabled' : 'Disabled'}
                      </Tag>
                    </div>
                  </div>
                </div>
                <Switch
                  checked={agent.enabled}
                  onChange={(checked) => {
                    if (checked) {
                      enableMutation.mutate(agent.id);
                    } else {
                      disableMutation.mutate(agent.id);
                    }
                  }}
                  size="small"
                />
              </div>

              {agent.description && (
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-3 line-clamp-2 leading-relaxed">
                  {agent.description}
                </p>
              )}

              <div className="space-y-2 text-xs text-gray-500 dark:text-gray-400">
                {agent.model && (
                  <div className="flex items-center gap-1.5">
                    <ApiOutlined className="flex-shrink-0" />
                    <span className="truncate">{agent.model}</span>
                  </div>
                )}
                {agent.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {agent.skills.slice(0, 3).map((skill) => (
                      <Tag key={skill} className="text-xs">{skill}</Tag>
                    ))}
                    {agent.skills.length > 3 && (
                      <Tag className="text-xs">+{agent.skills.length - 3}</Tag>
                    )}
                  </div>
                )}
                {agent.topics.length > 0 && (
                  <div className="flex items-center gap-1.5">
                    <BellOutlined className="flex-shrink-0" />
                    <span>{agent.topics.length} topics</span>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-1 mt-4 pt-3 border-t border-gray-200/80 dark:border-gray-700/60">
                <Tooltip title="Edit">
                  <Button
                    type="text"
                    size="small"
                    icon={<EditOutlined />}
                    onClick={() => handleEdit(agent)}
                  />
                </Tooltip>
                <Popconfirm
                  title="Confirm delete"
                  description="This will permanently delete this Agent"
                  onConfirm={() => deleteMutation.mutate(agent.id)}
                  okText="Delete"
                  cancelText="Cancel"
                  okButtonProps={{ danger: true }}
                >
                  <Tooltip title="Delete">
                    <Button
                      type="text"
                      size="small"
                      danger
                      icon={<DeleteOutlined />}
                    />
                  </Tooltip>
                </Popconfirm>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <Modal
        title="New Agent"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          resetForm();
        }}
        okText="Create"
        cancelText="Cancel"
        confirmLoading={createMutation.isPending}
        okButtonProps={{ disabled: !formData.name.trim() }}
        width={640}
        destroyOnClose
        styles={{ body: { maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form layout="vertical" className="pt-2">
          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide">
            Basic
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Agent Name" required>
            <Input
              placeholder="e.g. Code Reviewer, Doc Writer, Test Generator"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              onPressEnter={handleCreate}
            />
          </Form.Item>
          <Form.Item label="Description">
            <TextArea
              rows={2}
              placeholder="What does this agent do?"
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value || null })}
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            Model
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="Model">
              <Select
                placeholder="Select a model (default if empty)"
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
            System Prompt & Skills
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="System Prompt">
            <TextArea
              rows={4}
              placeholder="Define the agent's behavior and personality..."
              value={formData.system_prompt || ''}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value || null })}
            />
          </Form.Item>
          <Form.Item label="Skills">
            <Select
              mode="multiple"
              placeholder="Select skills"
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
            extra="Agent will subscribe to these topics for inter-agent communication"
          >
            <Select
              mode="tags"
              placeholder="Add topics (press Enter)"
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
        title={`Edit Agent: ${selectedAgent?.name ?? ''}`}
        open={editModalOpen}
        onOk={handleUpdate}
        onCancel={() => {
          setEditModalOpen(false);
          setSelectedAgent(null);
          resetForm();
        }}
        okText="Save"
        cancelText="Cancel"
        confirmLoading={updateMutation.isPending}
        okButtonProps={{ disabled: !formData.name.trim() }}
        width={640}
        destroyOnClose
        styles={{ body: { maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form layout="vertical" className="pt-2">
          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide">
            Basic
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Agent Name" required>
            <Input
              placeholder="e.g. Code Reviewer, Doc Writer"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
            />
          </Form.Item>
          <Form.Item label="Description">
            <TextArea
              rows={2}
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value || null })}
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            Model
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="Model">
              <Select
                placeholder="Select a model (default if empty)"
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
            System Prompt & Skills
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="System Prompt">
            <TextArea
              rows={4}
              value={formData.system_prompt || ''}
              onChange={(e) => setFormData({ ...formData, system_prompt: e.target.value || null })}
            />
          </Form.Item>
          <Form.Item label="Skills">
            <Select
              mode="multiple"
              placeholder="Select skills"
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
            extra="Agent will subscribe to these topics for inter-agent communication"
          >
            <Select
              mode="tags"
              placeholder="Add topics (press Enter)"
              value={formData.topics || []}
              onChange={(v) => setFormData({ ...formData, topics: v || [] })}
              tokenSeparators={[',']}
              className="w-full"
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            Status
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Enabled">
            <Switch
              checked={formData.enabled}
              onChange={(checked) => setFormData({ ...formData, enabled: checked })}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
