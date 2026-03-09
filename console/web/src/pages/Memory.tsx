import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Spin, Segmented, Empty, Card, Select } from 'antd';
import ReactMarkdown from 'react-markdown';
import * as api from '../api/client';
import { useAppStore } from '../store';

type TabKey = 'long_term' | 'history';

function parseHistoryEntries(historyText: string): { timestamp?: string; content: string }[] {
  if (!historyText.trim()) return [];
  const blocks = historyText.split(/\n\n+/).filter((b) => b.trim());
  return blocks.map((block) => {
    const match = block.match(/^\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})\]\s*(.*)/s);
    if (match) {
      return { timestamp: match[1], content: match[2].trim() };
    }
    return { content: block.trim() };
  });
}

export default function Memory() {
  const { currentBotId, setCurrentBotId } = useAppStore();
  const [activeTab, setActiveTab] = useState<TabKey>('long_term');

  const { data: bots } = useQuery({
    queryKey: ['bots'],
    queryFn: api.listBots,
  });

  const { data: memory, isLoading, error } = useQuery({
    queryKey: ['memory', currentBotId],
    queryFn: () => api.getMemory(currentBotId),
  });

  const historyEntries = memory?.history ? parseHistoryEntries(memory.history) : [];
  const longTermContent = memory?.long_term?.trim() ?? '';

  return (
    <div className="p-6 flex flex-col flex-1 min-h-0">
      <div className="flex items-center justify-between shrink-0">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
            记忆
          </h1>
          <p className="text-sm text-gray-500 mt-1">长期记忆与历史事件</p>
        </div>
        {bots && bots.length > 1 && (
          <Select
            value={currentBotId || bots.find((b) => b.is_default)?.id || bots[0]?.id}
            onChange={setCurrentBotId}
            options={bots.map((b) => ({ label: b.name, value: b.id }))}
            className="w-40"
          />
        )}
      </div>

      <Segmented
        value={activeTab}
        onChange={(val) => setActiveTab(val as TabKey)}
        size="large"
        options={[
          { value: 'long_term', label: '长期记忆' },
          { value: 'history', label: '历史事件' },
        ]}
        className="mb-1 shrink-0"
      />

      {isLoading ? (
        <div className="flex justify-center py-12 shrink-0">
          <Spin />
        </div>
      ) : error ? (
        <Empty
          description={
            <span className="text-red-500">
              {String(error).includes('404') ? 'Workspace not found' : String(error)}
            </span>
          }
        />
      ) : activeTab === 'long_term' ? (
        <Card
          className="flex-1 min-h-0 overflow-hidden border-0 shadow-sm bg-gradient-to-b from-white to-gray-50/50 dark:from-gray-800/50 dark:to-gray-900/50 flex flex-col"
          styles={{ body: { padding: '2rem 2.5rem', flex: 1, minHeight: 0, overflowY: 'auto' } }}
        >
          {longTermContent ? (
            <div className="max-w-3xl">
              <div
                className="
                  prose prose-slate dark:prose-invert
                  prose-headings:font-semibold prose-headings:tracking-tight
                  prose-h2:text-lg prose-h2:mt-8 prose-h2:mb-4 prose-h2:pb-2 prose-h2:border-b prose-h2:border-gray-200 dark:prose-h2:border-gray-700
                  prose-h3:text-base prose-h3:mt-6 prose-h3:mb-3
                  prose-p:leading-relaxed prose-p:text-gray-700 dark:prose-p:text-gray-300
                  prose-li:marker:text-blue-500 prose-ul:my-3
                  prose-strong:text-gray-900 dark:prose-strong:text-gray-100
                  prose-hr:my-8 prose-hr:border-gray-200 dark:prose-hr:border-gray-700
                "
              >
                <ReactMarkdown>{longTermContent}</ReactMarkdown>
              </div>
            </div>
          ) : (
            <Empty description="暂无长期记忆" />
          )}
        </Card>
      ) : (
        <div className="space-y-3">
          {historyEntries.length > 0 ? (
            historyEntries.map((entry, idx) => (
              <Card
                key={idx}
                size="small"
                className="border-l-4 border-l-blue-500 shadow-sm hover:shadow-md transition-shadow bg-white dark:bg-gray-800/50"
              >
                <div className="flex gap-4">
                  {entry.timestamp && (
                    <span className="text-xs font-mono text-blue-600 dark:text-blue-400 shrink-0 pt-0.5">
                      {entry.timestamp}
                    </span>
                  )}
                  <div className="flex-1 text-sm leading-relaxed text-gray-700 dark:text-gray-300 whitespace-pre-wrap">
                    {entry.content}
                  </div>
                </div>
              </Card>
            ))
          ) : (
            <Empty description="暂无历史事件" />
          )}
        </div>
      )}
    </div>
  );
}
