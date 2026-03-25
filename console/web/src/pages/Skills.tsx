import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Form,
  Input,
  Button,
  Spin,
  Typography,
  Space,
  Tag,
  Alert,
  Modal,
  Select,
  Empty,
  Switch,
} from 'antd';
import { ReadOutlined, EditOutlined, DeleteOutlined, PlusOutlined, EyeOutlined } from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import * as api from '../api/client';
import { useAppStore } from '../store';

const { Text } = Typography;

type SkillTabKey = 'builtin' | 'workspace';

const SKILL_TABS: { key: SkillTabKey; label: string }[] = [
  { key: 'builtin', label: 'Built-in Skills' },
  { key: 'workspace', label: 'Workspace Skills' },
];

type RegistrySkill = { name: string; description?: string; url?: string; version?: string };

/** Parse SKILL.md content to extract description and body (workspace skills have frontmatter). */
function parseSkillContent(full: string): { description: string; body: string } {
  const match = full.match(/^---\s*\n([\s\S]*?)\n---\s*\n?([\s\S]*)$/);
  if (!match) return { description: '', body: full };
  const [, frontmatter, body] = match;
  const descMatch = frontmatter.match(/description:\s*"((?:[^"\\]|\\.)*)"/);
  return {
    description: descMatch ? descMatch[1].replace(/\\"/g, '"') : '',
    body: (body || '').trim(),
  };
}

/** Build full SKILL.md content from name, description, and body. */
function buildSkillContent(name: string, description: string, body: string): string {
  const descEscaped = description.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n/g, ' ');
  return `---\nname: "${name}"\ndescription: "${descEscaped}"\n---\n\n${body}`;
}

export default function Skills() {
  const queryClient = useQueryClient();
  const { addToast, currentBotId, setCurrentBotId } = useAppStore();
  const [activeTab, setActiveTab] = useState<SkillTabKey>('builtin');
  const [skillViewModal, setSkillViewModal] = useState<{ name: string; content: string } | null>(null);
  const [skillViewMode, setSkillViewMode] = useState<'raw' | 'preview'>('preview');
  const [skillEditModal, setSkillEditModal] = useState<{
    name: string;
    content: string;
    description: string;
    body: string;
    isWorkspace: boolean;
  } | null>(null);
  const [skillCreateModal, setSkillCreateModal] = useState(false);
  const [skillCreateForm] = Form.useForm<{ name: string; description: string; content: string }>();
  const [registryUrl, setRegistryUrl] = useState('');
  const [registrySearch, setRegistrySearch] = useState('');

  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: api.listBots,
  });

  const { data: skills, isLoading: skillsLoading } = useQuery({
    queryKey: ['skills', currentBotId],
    queryFn: () => api.listSkills(currentBotId),
  });

  const { data: registrySkills = [], isLoading: registryLoading } = useQuery({
    queryKey: ['skills-registry', registryUrl, registrySearch, currentBotId],
    queryFn: () => api.searchSkillsRegistry(registrySearch || undefined, registryUrl || undefined, currentBotId),
    enabled: !!registryUrl.trim(),
  });

  const installFromRegistryMutation = useMutation({
    mutationFn: (name: string) =>
      api.installSkillFromRegistry(name, currentBotId, registryUrl || undefined),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Skill installed from registry' });
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
    onError: (e) => addToast({ type: 'error', message: String(e) }),
  });

  const updateConfigMutation = useMutation({
    mutationFn: ({ section, data }: { section: string; data: Record<string, unknown> }) =>
      api.updateConfig(section, data, currentBotId),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Settings saved successfully' });
      queryClient.invalidateQueries({ queryKey: ['config'] });
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const updateSkillContentMutation = useMutation({
    mutationFn: ({ name, content }: { name: string; content: string }) =>
      api.updateSkillContent(name, content, currentBotId),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Skill updated' });
      setSkillEditModal(null);
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const createSkillMutation = useMutation({
    mutationFn: (data: { name: string; description: string; content: string }) =>
      api.createSkill(data, currentBotId),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Skill created' });
      setSkillCreateModal(false);
      skillCreateForm.resetFields();
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const deleteSkillMutation = useMutation({
    mutationFn: (name: string) => api.deleteSkill(name, currentBotId),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Skill deleted' });
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const copyToWorkspaceMutation = useMutation({
    mutationFn: (name: string) => api.copySkillToWorkspace(name, currentBotId),
    onSuccess: () => {
      addToast({ type: 'success', message: 'Skill copied to workspace' });
      queryClient.invalidateQueries({ queryKey: ['skills'] });
    },
    onError: (error) => {
      addToast({ type: 'error', message: String(error) });
    },
  });

  const handleEditBuiltin = async (skill: { name: string; description: string }) => {
    try {
      await copyToWorkspaceMutation.mutateAsync(skill.name);
      setActiveTab('workspace');
      const res = await api.getSkillContent(skill.name, currentBotId);
      const { description, body } = parseSkillContent(res.content);
      setSkillEditModal({
        name: res.name,
        content: res.content,
        description: description || skill.description,
        body,
        isWorkspace: true,
      });
    } catch {
      // Error already handled by mutation
    }
  };

  const SkillItemCard = ({
    skill,
    source,
    children,
  }: {
    skill: { name: string; description?: string; available?: boolean };
    source: 'builtin' | 'workspace';
    children: React.ReactNode;
  }) => (
    <div
      className={`
        group flex items-center justify-between gap-4 px-5 py-4 rounded-xl
        border border-gray-200/70 dark:border-gray-700/60
        bg-white dark:bg-gray-800/50
        hover:border-primary-300/60 dark:hover:border-primary-500/40
        hover:shadow-md hover:shadow-primary-500/5 dark:hover:shadow-primary-500/10
        transition-all duration-200
      `}
    >
      <div className="flex items-center gap-4 min-w-0 flex-1">
        <div className="flex-shrink-0 w-10 h-10 rounded-xl bg-gradient-to-br from-primary-50 to-primary-100 dark:from-primary-900/40 dark:to-primary-800/30 flex items-center justify-center">
          <ReadOutlined className="text-primary-500 dark:text-primary-400 text-base" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-gray-900 dark:text-gray-100 truncate">{skill.name}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-1 hidden sm:block">
            {skill.description || 'No description'}
          </p>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          <Tag color={source === 'builtin' ? 'blue' : 'green'} className="!m-0">
            {source}
          </Tag>
          {skill.available === false && (
            <Tag color="warning" className="!m-0">unavailable</Tag>
          )}
        </div>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">{children}</div>
    </div>
  );

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 via-primary-700 to-gray-700 dark:from-white dark:via-primary-300 dark:to-gray-300 bg-clip-text text-transparent">
            Skills
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 hidden sm:block">
            Manage built-in and workspace skills
          </p>
        </div>
        <Space>
          {bots && bots.length > 1 && (
            <Select
              value={currentBotId || bots.find((b) => b.is_default)?.id || bots[0]?.id}
              onChange={setCurrentBotId}
              options={bots.map((b) => ({ label: b.name, value: b.id }))}
              className="w-40"
            />
          )}
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setSkillCreateModal(true)}
            className="shadow-md shadow-primary-500/25"
          >
            <span className="hidden sm:inline">Add Skill</span>
          </Button>
        </Space>
      </div>

      {/* Registry Install Section */}
      <div className="mt-6 p-5 rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 mb-1">
          Install from Registry
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          Registry URL (JSON format). Load skills and install with one click.
        </p>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <Input
              placeholder="Registry URL e.g. https://example.com/registry.json"
              value={registryUrl}
              onChange={(e) => setRegistryUrl(e.target.value)}
              className="flex-1 min-w-[200px] border-gray-300 dark:border-gray-600 hover:border-primary-400 focus:border-primary-500"
            />
            <Input
              placeholder="Search skill name or description"
              value={registrySearch}
              onChange={(e) => setRegistrySearch(e.target.value)}
              className="w-64"
              onPressEnter={() => queryClient.invalidateQueries({ queryKey: ['skills-registry'] })}
            />
            <Button
              type="default"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['skills-registry'] })}
              loading={registryLoading}
              className="border-gray-300 dark:border-gray-600 hover:border-primary-400 hover:text-primary-500 shrink-0"
            >
              Search
            </Button>
          </div>
          {registryUrl.trim() && (
            registrySkills.length === 0 ? (
              <Empty description={registryLoading ? 'Loading...' : 'No skills found or registry empty'} />
            ) : (
              <div className="space-y-3">
                {registrySkills.map((s: RegistrySkill) => {
                  const installed = skills?.some((sk) => sk.name === s.name);
                  return (
                    <div
                      key={s.name}
                      className="flex items-center justify-between px-4 py-3 rounded-xl bg-gray-50 dark:bg-gray-800/60 border border-gray-100 dark:border-gray-700/50 hover:border-primary-200 dark:hover:border-primary-500/30 transition-colors"
                    >
                      <div>
                        <p className="font-medium text-gray-900 dark:text-gray-100">{s.name}</p>
                        <Text type="secondary" className="text-xs">
                          {s.description || '-'}
                        </Text>
                      </div>
                      <Button
                        type="primary"
                        size="small"
                        disabled={!!installed}
                        loading={installFromRegistryMutation.isPending}
                        onClick={() => installFromRegistryMutation.mutate(s.name)}
                        className="!rounded-lg"
                      >
                        {installed ? 'Installed' : 'Install'}
                      </Button>
                    </div>
                  );
                })}
              </div>
            )
          )}
        </div>
      </div>

      {skillsLoading ? (
        <div className="flex justify-center py-12 shrink-0">
          <Spin size="large" />
        </div>
      ) : !skills || skills.length === 0 ? (
        <Empty description="No skills found" className="shrink-0" />
      ) : (
        <>
          <Alert
            className="shrink-0 mt-6 rounded-xl border-0"
            title="Changes require restart"
            description="Skill enable/disable or content changes take effect after restarting the bot."
            type="info"
            showIcon
          />
          {/* Tabs with underline indicator */}
          <div className="flex border-b border-gray-200 dark:border-gray-700 mt-6 mb-4 gap-0">
            {SKILL_TABS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`
                  relative px-6 py-3 text-sm font-medium transition-all duration-200
                  ${activeTab === key
                    ? 'text-primary-600 dark:text-primary-400'
                    : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                  }
                `}
              >
                {label}
                {activeTab === key && (
                  <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary-500 rounded-full" />
                )}
              </button>
            ))}
          </div>

          <div className="flex-1 min-h-0 overflow-y-auto pt-2">
            {activeTab === 'builtin' ? (
              <div className="space-y-4">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                  Enable or disable built-in skills
                </p>
                {skills.filter((s) => s.source === 'builtin').length === 0 ? (
                  <Empty description="No built-in skills" />
                ) : (
                  <div className="space-y-3">
                    {skills
                      .filter((s) => s.source === 'builtin')
                      .map((skill) => (
                        <SkillItemCard key={skill.name} skill={skill} source="builtin">
                          <Button
                            type="text"
                            size="middle"
                            icon={<EditOutlined />}
                            onClick={() => handleEditBuiltin(skill)}
                            loading={copyToWorkspaceMutation.isPending}
                            className="text-gray-600 dark:text-gray-400 hover:text-primary-500"
                          >
                            Edit
                          </Button>
                          <Button
                            type="text"
                            size="middle"
                            icon={<EyeOutlined />}
                            onClick={async () => {
                              const res = await api.getSkillContent(skill.name, currentBotId);
                              setSkillViewModal({ name: res.name, content: res.content });
                              setSkillViewMode('preview');
                            }}
                            className="text-gray-600 dark:text-gray-400 hover:text-primary-500"
                          >
                            View
                          </Button>
                          <Switch
                            checked={skill.enabled}
                            onChange={(checked) =>
                              updateConfigMutation.mutate({
                                section: 'skills',
                                data: { [skill.name]: { enabled: checked } },
                              })
                            }
                          />
                        </SkillItemCard>
                      ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
                  Edit or delete workspace skills
                </p>
                {skills.filter((s) => s.source === 'workspace').length === 0 ? (
                  <Empty description="No workspace skills" />
                ) : (
                  <div className="space-y-3">
                    {skills
                      .filter((s) => s.source === 'workspace')
                      .map((skill) => (
                        <SkillItemCard key={skill.name} skill={skill} source="workspace">
                          <Button
                            type="text"
                            size="middle"
                            icon={<EditOutlined />}
                            onClick={async () => {
                              const res = await api.getSkillContent(skill.name, currentBotId);
                              const { description, body } = parseSkillContent(res.content);
                              setSkillEditModal({
                                name: res.name,
                                content: res.content,
                                description: description || skill.description,
                                body,
                                isWorkspace: true,
                              });
                            }}
                            className="text-gray-600 dark:text-gray-400 hover:text-primary-500"
                          >
                            Edit
                          </Button>
                          <Button
                            type="text"
                            danger
                            size="middle"
                            icon={<DeleteOutlined />}
                            onClick={() => {
                              Modal.confirm({
                                title: `Delete skill "${skill.name}"?`,
                                content: 'This cannot be undone.',
                                okText: 'Delete',
                                okType: 'danger',
                                onOk: () => deleteSkillMutation.mutate(skill.name),
                              });
                            }}
                            className="hover:!text-red-500"
                          >
                            Delete
                          </Button>
                        </SkillItemCard>
                      ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}

      <Modal
        title={`View skill: ${skillViewModal?.name}`}
        open={!!skillViewModal}
        onCancel={() => setSkillViewModal(null)}
        footer={
          <div className="flex items-center justify-between w-full">
            <div className="flex gap-1">
              <button
                type="button"
                onClick={() => setSkillViewMode('preview')}
                className={`px-3 py-1 rounded text-sm ${skillViewMode === 'preview' ? 'bg-primary-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
              >
                Preview
              </button>
              <button
                type="button"
                onClick={() => setSkillViewMode('raw')}
                className={`px-3 py-1 rounded text-sm ${skillViewMode === 'raw' ? 'bg-primary-500 text-white' : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
              >
                Raw
              </button>
            </div>
            <Button onClick={() => setSkillViewModal(null)}>Close</Button>
          </div>
        }
        width={700}
        destroyOnHidden
      >
        {skillViewModal && (
          <div className="overflow-auto max-h-[60vh]">
            {skillViewMode === 'raw' ? (
              <pre className="p-4 rounded-lg bg-gray-50 dark:bg-gray-900 text-sm font-mono whitespace-pre-wrap">
                {skillViewModal.content}
              </pre>
            ) : (
              <div className="p-4 prose prose-slate dark:prose-invert prose-sm max-w-none">
                <ReactMarkdown>{skillViewModal.content}</ReactMarkdown>
              </div>
            )}
          </div>
        )}
      </Modal>

      <Modal
        title={`Edit skill: ${skillEditModal?.name}`}
        open={!!skillEditModal}
        onCancel={() => setSkillEditModal(null)}
        footer={null}
        width={700}
        destroyOnHidden
      >
        {skillEditModal && skillEditModal.isWorkspace && (
          <Form
            key={skillEditModal.name}
            layout="vertical"
            initialValues={{
              description: skillEditModal.description,
              body: skillEditModal.body,
            }}
            onFinish={(values) => {
              const content = buildSkillContent(
                skillEditModal.name,
                values.description,
                values.body
              );
              updateSkillContentMutation.mutate({
                name: skillEditModal.name,
                content,
              });
            }}
          >
            <Form.Item name="description" label="Description" rules={[{ required: true }]}>
              <Input placeholder="Brief description of the skill" />
            </Form.Item>
            <Form.Item name="body" label="Content (SKILL.md body)" rules={[{ required: true }]}>
              <Input.TextArea rows={14} className="font-mono text-sm" placeholder="# Skill instructions..." />
            </Form.Item>
            <Form.Item className="!mb-0">
              <Space>
                <Button onClick={() => setSkillEditModal(null)}>Cancel</Button>
                <Button
                  type="primary"
                  htmlType="submit"
                  loading={updateSkillContentMutation.isPending}
                >
                  Save
                </Button>
              </Space>
            </Form.Item>
          </Form>
        )}
      </Modal>

      <Modal
        title="Create Workspace Skill"
        open={skillCreateModal}
        onCancel={() => {
          setSkillCreateModal(false);
          skillCreateForm.resetFields();
        }}
        footer={null}
        destroyOnHidden
      >
        <Form
          form={skillCreateForm}
          layout="vertical"
          onFinish={(values) =>
            createSkillMutation.mutate({
              name: values.name,
              description: values.description,
              content: values.content || '',
            })
          }
        >
          <Form.Item
            name="name"
            label="Name"
            rules={[
              { required: true },
              {
                pattern: /^[a-zA-Z0-9_-]+$/,
                message: 'Only letters, numbers, underscore, hyphen',
              },
            ]}
          >
            <Input placeholder="my-skill" />
          </Form.Item>
          <Form.Item name="description" label="Description" rules={[{ required: true }]}>
            <Input placeholder="Brief description of the skill" />
          </Form.Item>
          <Form.Item name="content" label="Content (SKILL.md body)">
            <Input.TextArea rows={8} placeholder="# Skill instructions..." />
          </Form.Item>
          <Form.Item className="!mb-0">
            <Space>
              <Button
                onClick={() => {
                  setSkillCreateModal(false);
                  skillCreateForm.resetFields();
                }}
              >
                Cancel
              </Button>
              <Button
                type="primary"
                htmlType="submit"
                loading={createSkillMutation.isPending}
              >
                Create
              </Button>
            </Space>
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
