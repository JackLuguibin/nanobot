import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Card, Modal, Input, Tag, Tooltip, Empty, Popconfirm, Spin } from 'antd';
import {
  PlusOutlined,
  DeleteOutlined,
  StarOutlined,
  StarFilled,
} from '@ant-design/icons';
import { Bot, FolderOpen, Clock, Settings } from 'lucide-react';
import { useAppStore } from '../store';
import * as api from '../api/client';
import type { BotInfo } from '../api/types';

export default function Bots() {
  const queryClient = useQueryClient();
  const { currentBotId, setCurrentBotId, addToast } = useAppStore();
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [newBotName, setNewBotName] = useState('');

  const { data: bots = [], isLoading } = useQuery({
    queryKey: ['bots'],
    queryFn: api.listBots,
    refetchInterval: 10000,
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => api.createBot(name),
    onSuccess: (bot) => {
      queryClient.invalidateQueries({ queryKey: ['bots'] });
      addToast({ type: 'success', message: `Bot "${bot.name}" 创建成功` });
      setCreateModalOpen(false);
      setNewBotName('');
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `创建失败: ${err.message}` });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (botId: string) => api.deleteBot(botId),
    onSuccess: (_, botId) => {
      queryClient.invalidateQueries({ queryKey: ['bots'] });
      if (currentBotId === botId) {
        setCurrentBotId(null);
      }
      addToast({ type: 'success', message: 'Bot 已删除' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `删除失败: ${err.message}` });
    },
  });

  const setDefaultMutation = useMutation({
    mutationFn: (botId: string) => api.setDefaultBot(botId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['bots'] });
      addToast({ type: 'success', message: '默认 Bot 已更新' });
    },
    onError: (err: Error) => {
      addToast({ type: 'error', message: `设置默认失败: ${err.message}` });
    },
  });

  const handleCreate = () => {
    if (newBotName.trim()) {
      createMutation.mutate(newBotName.trim());
    }
  };

  const handleSelect = (botId: string) => {
    setCurrentBotId(botId);
    addToast({ type: 'info', message: '已切换当前 Bot' });
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
            Bot 管理
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            管理多个 Bot 实例，每个 Bot 拥有独立的配置和工作空间
          </p>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateModalOpen(true)}
        >
          新建 Bot
        </Button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-20">
          <Spin size="large" />
        </div>
      ) : bots.length === 0 ? (
        <Empty
          description="暂无 Bot，点击右上角创建"
          className="py-20"
        />
      ) : (
        <div className="grid gap-4 grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
          {bots.map((bot) => {
            const isActive = currentBotId === bot.id;
            return (
              <Card
                key={bot.id}
                className={`cursor-pointer transition-all duration-200 hover:shadow-md ${
                  isActive
                    ? 'ring-2 ring-blue-500 dark:ring-blue-400'
                    : 'hover:ring-1 hover:ring-gray-300 dark:hover:ring-gray-600'
                }`}
                onClick={() => handleSelect(bot.id)}
                styles={{ body: { padding: 20 } }}
              >
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                      isActive
                        ? 'bg-blue-100 dark:bg-blue-900/40'
                        : 'bg-gray-100 dark:bg-gray-800'
                    }`}>
                      <Bot className={`w-5 h-5 ${
                        isActive ? 'text-blue-600 dark:text-blue-400' : 'text-gray-500 dark:text-gray-400'
                      }`} />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900 dark:text-gray-100 text-sm">
                        {bot.name}
                      </h3>
                      <div className="flex items-center gap-1.5 mt-0.5">
                        {bot.is_default && (
                          <Tag color="blue" className="text-xs !mr-0">默认</Tag>
                        )}
                        <Tag
                          color={bot.running ? 'green' : 'default'}
                          className="text-xs !mr-0"
                        >
                          {bot.running ? '运行中' : '已停止'}
                        </Tag>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="space-y-1.5 text-xs text-gray-500 dark:text-gray-400">
                  <div className="flex items-center gap-1.5">
                    <FolderOpen className="w-3.5 h-3.5 flex-shrink-0" />
                    <Tooltip title={bot.workspace_path}>
                      <span className="truncate block max-w-[200px]">
                        {bot.workspace_path}
                      </span>
                    </Tooltip>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5 flex-shrink-0" />
                    <span>
                      {bot.created_at
                        ? new Date(bot.created_at).toLocaleDateString('zh-CN')
                        : '未知'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-end gap-1 mt-3 pt-3 border-t border-gray-100 dark:border-gray-800">
                  {!bot.is_default && (
                    <Tooltip title="设为默认">
                      <Button
                        type="text"
                        size="small"
                        icon={<StarOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          setDefaultMutation.mutate(bot.id);
                        }}
                      />
                    </Tooltip>
                  )}
                  {bot.is_default && (
                    <Tooltip title="当前默认">
                      <Button
                        type="text"
                        size="small"
                        icon={<StarFilled className="text-yellow-500" />}
                        disabled
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Tooltip>
                  )}
                  <Popconfirm
                    title="确认删除"
                    description="将同时删除该 Bot 的配置和工作空间数据"
                    onConfirm={(e) => {
                      e?.stopPropagation();
                      deleteMutation.mutate(bot.id);
                    }}
                    onCancel={(e) => e?.stopPropagation()}
                    okText="删除"
                    cancelText="取消"
                    okButtonProps={{ danger: true }}
                  >
                    <Tooltip title="删除">
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        onClick={(e) => e.stopPropagation()}
                      />
                    </Tooltip>
                  </Popconfirm>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      <Modal
        title="新建 Bot"
        open={createModalOpen}
        onOk={handleCreate}
        onCancel={() => {
          setCreateModalOpen(false);
          setNewBotName('');
        }}
        okText="创建"
        cancelText="取消"
        confirmLoading={createMutation.isPending}
        okButtonProps={{ disabled: !newBotName.trim() }}
      >
        <div className="py-4">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Bot 名称
          </label>
          <Input
            placeholder="例如：工作助手、代码审查、翻译助手"
            value={newBotName}
            onChange={(e) => setNewBotName(e.target.value)}
            onPressEnter={handleCreate}
            autoFocus
          />
          <p className="text-xs text-gray-400 dark:text-gray-500 mt-2">
            每个 Bot 都有独立的配置、工作空间和会话历史
          </p>
        </div>
      </Modal>
    </div>
  );
}
