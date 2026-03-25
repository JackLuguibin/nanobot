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

// Built-in categories (never persisted; always available)
const BUILTIN_CATEGORIES = [
  { key: 'all', label: 'All', color: '#1890ff' },
  { key: 'general', label: 'General', color: '#52c41a' },
  { key: 'content', label: 'Content', color: '#ff7875' },
  { key: 'office', label: 'Office', color: '#faad14' },
] as const;

type CategoryDef = { key: string; label: string; color: string };

function findCategoryConfig(key: string, custom: CategoryDef[]): CategoryDef {
  const built = BUILTIN_CATEGORIES.find((c) => c.key === key);
  if (built) return { ...built };
  const c = custom.find((x) => x.key === key);
  if (c) return c;
  return { ...BUILTIN_CATEGORIES[1] };
}

// Infer category from agent name or description
function getAgentCategory(agent: Agent): string {
  const name = agent.name.toLowerCase();
  const desc = (agent.description || '').toLowerCase();
  const text = `${name} ${desc}`;

  if (text.includes('content') || text.includes('creator')) {
    return 'content';
  }
  if (text.includes('office') || text.includes('enterprise')) {
    return 'office';
  }
  return 'general';
}

function resolveAgentCategory(agent: Agent, overrides: Record<string, string>): string {
  const o = overrides[agent.id];
  if (o) return o;
  return getAgentCategory(agent);
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
  const [addCategoryModalOpen, setAddCategoryModalOpen] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');
  const [createFormCategory, setCreateFormCategory] = useState('general');
  const [editFormCategory, setEditFormCategory] = useState('general');
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

  // Custom categories from API
  const { data: customCategories = [], refetch: refetchCategories } = useQuery({
    queryKey: ['agent-categories', currentBotId],
    queryFn: () => api.listCategories(currentBotId!),
    enabled: !!currentBotId,
  });

  // Category overrides from API
  const { data: categoryOverrides = {} } = useQuery({
    queryKey: ['agent-category-overrides', currentBotId],
    queryFn: () => api.getCategoryOverrides(currentBotId!),
    enabled: !!currentBotId,
  });

  const allCategoryTabs = useMemo(
    () => [...BUILTIN_CATEGORIES.map((c) => ({ ...c })), ...customCategories],
    [customCategories],
  );

  const selectableCategories = useMemo(
    () => allCategoryTabs.filter((c) => c.key !== 'all'),
    [allCategoryTabs],
  );

  // Filter agents by category
  const filteredAgents = useMemo(() => {
    if (selectedCategory === 'all') return agents;
    return agents.filter(
      (agent) => resolveAgentCategory(agent, categoryOverrides) === selectedCategory,
    );
  }, [agents, selectedCategory, categoryOverrides]);

  const addCategoryMutation = useMutation({
    mutationFn: (label: string) => api.addCategory(currentBotId!, label),
    onSuccess: (cat) => {
      refetchCategories();
      setSelectedCategory(cat.key);
      setNewCategoryName('');
      setAddCategoryModalOpen(false);
      addToast({ type: 'success', message: `Category "${cat.label}" added` });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Failed to add category: ${err.message}` });
    },
  });

  const createMutation = useMutation({
    mutationFn: (data: AgentCreateRequest & { displayCategory?: string }) =>
      api.createAgent(currentBotId!, data),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      queryClient.invalidateQueries({ queryKey: ['agents-status', currentBotId] });
      addToast({ type: 'success', message: `Agent "${agent.name}" created` });
      setCreateModalOpen(false);
      resetForm();
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Failed to create: ${err.message}` });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({
      agentId,
      data,
    }: {
      agentId: string;
      data: Partial<Agent>;
      displayCategory?: string;
    }) => api.updateAgent(currentBotId!, agentId, data),
    onSuccess: (agent) => {
      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      addToast({ type: 'success', message: `Agent "${agent.name}" updated` });
      setEditModalOpen(false);
      setSelectedAgent(null);
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `Failed to update: ${err.message}` });
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
      addToast({ type: 'error', message: `Failed to delete: ${err.message}` });
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
      addToast({ type: 'error', message: `Failed to enable: ${err.message}` });
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
      addToast({ type: 'error', message: `Failed to disable: ${err.message}` });
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
    setCreateFormCategory('general');
  };

  const handleCreate = () => {
    if (formData.name.trim()) {
      createMutation.mutate({ ...formData, displayCategory: createFormCategory });
    }
  };

  const handleConfirmAddCategory = () => {
    const label = newCategoryName.trim();
    if (!label) {
      addToast({ type: 'error', message: 'Please enter a category name' });
      return;
    }
    addCategoryMutation.mutate(label);
  };

  const handleEdit = (agent: Agent) => {
    setSelectedAgent(agent);
    setEditFormCategory(resolveAgentCategory(agent, categoryOverrides));
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
      updateMutation.mutate({
        agentId: selectedAgent.id,
        data: formData,
        displayCategory: editFormCategory,
      });
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
    addToast({ type: 'success', message: 'Export successful' });
  };

  const handleImport = async (file: File) => {
    try {
      const text = await file.text();
      const importedAgents = JSON.parse(text);

      if (!Array.isArray(importedAgents)) {
        throw new Error('Invalid import file format');
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
          console.error('Failed to import agent:', err);
        }
      }

      queryClient.invalidateQueries({ queryKey: ['agents', currentBotId] });
      addToast({
        type: successCount > 0 ? 'success' : 'error',
        message: `Import complete: ${successCount} succeeded, ${errorCount} failed`,
      });
      setImportModalOpen(false);
    } catch (err) {
      addToast({ type: 'error', message: `Import failed: ${err instanceof Error ? err.message : 'Unknown error'}` });
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
        <Empty description="Please select a Bot first" className="py-20" />
      </div>
    );
  }

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0 mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Agents
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1.5 hidden sm:block">
            Manage multiple AI Agents, each with independent configuration and capabilities
          </p>
        </div>
        <Space align="center" size="middle">
          {systemStatus && (
            <Tag 
              icon={<Radio className="w-3 h-3" />} 
              color={systemStatus.zmq_initialized ? 'success' : 'default'}
              className="!m-0"
            >
              ZeroMQ: {systemStatus.zmq_initialized ? 'Connected' : 'Disconnected'}
            </Tag>
          )}
          <Button
            icon={<ReloadOutlined />}
            onClick={() => refetch()}
            className="border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500"
          >
            <span className="hidden sm:inline">Refresh</span>
          </Button>
          <Button
            icon={<UploadOutlined />}
            onClick={() => setImportModalOpen(true)}
            className="border-gray-300 dark:border-gray-600 hover:border-gray-400 dark:hover:border-gray-500"
          >
            <span className="hidden sm:inline">Import</span>
          </Button>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              resetForm();
              setCreateModalOpen(true);
            }}
            className="shadow-md shadow-blue-500/25"
          >
            <span className="hidden sm:inline">New Agent</span>
          </Button>
        </Space>
      </div>

      {/* Category Filter */}
      <div className="flex items-center gap-2.5 mb-6 flex-wrap">
        {allCategoryTabs.map((cat) => (
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
          type="button"
          onClick={() => {
            setNewCategoryName('');
            setAddCategoryModalOpen(true);
          }}
          className="px-5 py-2 rounded-full text-sm font-medium border border-dashed border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-all"
        >
          + Add Category
        </button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="flex justify-center py-12 shrink-0">
          <Spin size="large" />
        </div>
      ) : error ? (
        <Empty description={`Error: ${(error as Error).message}`} className="py-12 shrink-0" />
      ) : filteredAgents.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <Empty
            description={
              <span className="text-gray-500 dark:text-gray-400">
                No agents yet — click the button above to create one
              </span>
            }
            className="py-12"
          />
        </div>
      ) : (
        <div className="w-full grid gap-3 grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5">
          {filteredAgents.map((agent) => {
            const category = resolveAgentCategory(agent, categoryOverrides);
            const categoryConfig = findCategoryConfig(category, customCategories);
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
                            SYS
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
                    <Tooltip title="Edit">
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
                    <Tooltip title="Export">
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
                      addToast({ type: 'success', message: 'Export successful' });
                        }}
                        className="text-gray-500 dark:text-gray-400 hover:text-green-500 dark:hover:text-green-400 !px-1"
                      />
                    </Tooltip>
                    <Popconfirm
                      title="Confirm Hide"
                      description="Are you sure you want to hide this Agent?"
                      onConfirm={(e) => {
                        e?.stopPropagation();
                        disableMutation.mutate(agent.id);
                      }}
                      okText="Hide"
                      cancelText="Cancel"
                      okButtonProps={{ danger: true }}
                    >
                      <Tooltip title="Hide">
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
                  <span className="text-blue-500 font-semibold">{selectedAgents.size}</span> Agent{selectedAgents.size > 1 ? 's' : ''} selected
                </span>
              <Divider type="vertical" className="!my-0" />
              <Button size="small" onClick={handleSelectAll}>
                {selectedAgents.size === filteredAgents.length ? 'Deselect All' : 'Select All'}
              </Button>
              <Button size="small" icon={<DownloadOutlined />} onClick={handleExport}>
                Batch Export
              </Button>
              <Button
                size="small"
                danger
                icon={<DeleteOutlined />}
                onClick={() => {
                  Modal.confirm({
                    title: 'Confirm Delete',
                    content: `Are you sure you want to delete ${selectedAgents.size} selected Agent${selectedAgents.size > 1 ? 's' : ''}? This cannot be undone.`,
                    okText: 'Delete',
                    okType: 'danger',
                    cancelText: 'Cancel',
                    onOk: () => {
                      selectedAgents.forEach((id) => {
                        deleteMutation.mutate(id);
                      });
                      setSelectedAgents(new Set());
                    },
                  });
                }}
              >
                Batch Delete
              </Button>
            </Space>
          </Card>
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
        destroyOnHidden
        styles={{ body: { maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form layout="vertical" className="pt-2">
          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide">
            Basic Info
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Agent Name" required>
            <Input
              placeholder="e.g. Code Review, Documentation, Test Generation"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              onPressEnter={handleCreate}
            />
          </Form.Item>
          <Form.Item label="Description">
            <TextArea
              rows={2}
              placeholder="What does this Agent do?"
              value={formData.description || ''}
              onChange={(e) => setFormData({ ...formData, description: e.target.value || null })}
            />
          </Form.Item>
          <Form.Item label="Display Category" extra="Used for list filtering and tag colors; custom categories can be created via + Add Category">
            <Select
              value={createFormCategory}
              onChange={(v) => setCreateFormCategory(v)}
              options={selectableCategories.map((c) => ({
                value: c.key,
                label: c.label,
              }))}
              className="w-full"
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            Model Config
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="Model">
              <Select
                placeholder="Select model (defaults to global if empty)"
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
              placeholder="Define the Agent's behavior and personality..."
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
            extra="The Agent subscribes to these topics for inter-Agent communication"
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
        destroyOnHidden
        styles={{ body: { maxHeight: '60vh', overflowY: 'auto' } }}
      >
        <Form layout="vertical" className="pt-2">
          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide">
            Basic Info
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <Form.Item label="Agent Name" required>
            <Input
              placeholder="e.g. Code Review, Documentation"
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
          <Form.Item label="Display Category" extra="Used for list filtering and tag colors">
            <Select
              value={editFormCategory}
              onChange={(v) => setEditFormCategory(v)}
              options={selectableCategories.map((c) => ({
                value: c.key,
                label: c.label,
              }))}
              className="w-full"
            />
          </Form.Item>

          <Typography.Text type="secondary" strong className="text-xs uppercase tracking-wide mt-4 block">
            Model Config
          </Typography.Text>
          <Divider className="!mt-1 !mb-3" />
          <div className="grid grid-cols-2 gap-4">
            <Form.Item label="Model">
              <Select
                placeholder="Select model (defaults to global if empty)"
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
            extra="The Agent subscribes to these topics for inter-Agent communication"
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

      <Modal
        title="Add Category"
        open={addCategoryModalOpen}
        onOk={handleConfirmAddCategory}
        onCancel={() => {
          setAddCategoryModalOpen(false);
          setNewCategoryName('');
        }}
        okText="Add"
        cancelText="Cancel"
        destroyOnHidden
      >
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-3">
          New categories appear in the filter tabs. Assign an Agent to a category via the Display Category field when creating or editing.
        </p>
        <Input
          placeholder="Category name"
          value={newCategoryName}
          onChange={(e) => setNewCategoryName(e.target.value)}
          onPressEnter={handleConfirmAddCategory}
          maxLength={32}
          showCount
        />
      </Modal>

      {/* Import Modal */}
      <Modal
        title="Import Agent"
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
            <p className="ant-upload-text">Click or drag a file to upload</p>
            <p className="ant-upload-hint">Supports JSON-formatted Agent configuration files</p>
          </Upload.Dragger>
        </div>
      </Modal>
    </div>
  );
}
