import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Form,
  Input,
  Button,
  Spin,
  Card,
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

const { Title, Text } = Typography;

type SkillTabKey = 'builtin' | 'workspace';

const SKILL_TABS: { key: SkillTabKey; label: string }[] = [
  { key: 'builtin', label: 'Built-in Skills' },
  { key: 'workspace', label: 'Workspace Skills' },
];

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

  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: api.listBots,
  });

  const { data: skills, isLoading: skillsLoading } = useQuery({
    queryKey: ['skills', currentBotId],
    queryFn: () => api.listSkills(currentBotId),
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

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            Skills
          </h1>
          <p className="text-sm text-gray-500 mt-1 hidden sm:block">Manage built-in and workspace skills</p>
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
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setSkillCreateModal(true)}>
            <span className="hidden sm:inline">Add Skill</span>
          </Button>
        </Space>
      </div>

      {skillsLoading ? (
        <div className="flex justify-center py-12 shrink-0">
          <Spin />
        </div>
      ) : !skills || skills.length === 0 ? (
        <Empty description="No skills found" className="shrink-0" />
      ) : (
        <>
          <Alert
            className="shrink-0 mt-4"
            message="Changes require restart"
            description="Skill enable/disable or content changes take effect after restarting the bot."
            type="info"
            showIcon
          />
          <div className="flex flex-wrap gap-1 p-1 rounded-xl bg-gray-100/80 dark:bg-gray-800/50 border border-gray-200/60 dark:border-gray-700/50 w-fit shrink-0 mt-4 mb-3">
            {SKILL_TABS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                  activeTab === key
                    ? 'bg-white dark:bg-gray-700/80 text-gray-900 dark:text-gray-100 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <Card
            className="flex-1 min-h-0 overflow-hidden flex flex-col rounded-2xl border border-gray-200/80 dark:border-gray-700/60 bg-white dark:bg-gray-800/40 shadow-sm hover:shadow-md transition-shadow"
            styles={{ body: { padding: '1.5rem 2rem', flex: 1, minHeight: 0, overflowY: 'auto' } }}
          >
            {activeTab === 'builtin' ? (
              <div className="space-y-4">
                <Title level={5} className="!text-sm !mb-3">
                  Enable or disable built-in skills
                </Title>
                {skills.filter((s) => s.source === 'builtin').length === 0 ? (
                  <Empty description="No built-in skills" />
                ) : (
                <div className="space-y-2">
                  {skills
                    .filter((s) => s.source === 'builtin')
                    .map((skill) => (
                      <Card key={skill.name} size="small" className="w-full">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <ReadOutlined className="text-gray-500" />
                            <div>
                              <p className="font-medium">{skill.name}</p>
                              <Text type="secondary" className="text-xs hidden sm:block">
                                {skill.description}
                              </Text>
                            </div>
                            <Tag color="blue">builtin</Tag>
                            {skill.available === false && (
                              <Tag color="warning">unavailable</Tag>
                            )}
                          </div>
                          <Space>
                            <Button
                              type="text"
                              size="small"
                              icon={<EditOutlined />}
                              onClick={() => handleEditBuiltin(skill)}
                              loading={copyToWorkspaceMutation.isPending}
                            >
                              Edit
                            </Button>
                            <Button
                              type="text"
                              size="small"
                              icon={<EyeOutlined />}
                              onClick={async () => {
                                const res = await api.getSkillContent(skill.name, currentBotId);
                                setSkillViewModal({ name: res.name, content: res.content });
                                setSkillViewMode('preview');
                              }}
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
                          </Space>
                        </div>
                      </Card>
                    ))}
                </div>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <Title level={5} className="!text-sm !mb-3">
                  Edit or delete workspace skills
                </Title>
                {skills.filter((s) => s.source === 'workspace').length === 0 ? (
                  <Empty description="No workspace skills" />
                ) : (
                <div className="space-y-2">
                  {skills
                    .filter((s) => s.source === 'workspace')
                    .map((skill) => (
                      <Card key={skill.name} size="small" className="w-full">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <ReadOutlined className="text-gray-500" />
                            <div>
                              <p className="font-medium">{skill.name}</p>
                              <Text type="secondary" className="text-xs hidden sm:block">
                                {skill.description}
                              </Text>
                            </div>
                            <Tag color="green">workspace</Tag>
                          </div>
                          <Space>
                            <Button
                              type="text"
                              size="small"
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
                            >
                              Edit
                            </Button>
                            <Button
                              type="text"
                              danger
                              size="small"
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
                            >
                              Delete
                            </Button>
                          </Space>
                        </div>
                      </Card>
                    ))}
                </div>
                )}
              </div>
            )}
          </Card>
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
        destroyOnClose
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
        destroyOnClose
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
        destroyOnClose
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
