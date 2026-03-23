import { Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider, theme as antdTheme, App as AntdApp } from 'antd';
import { useEffect, useState } from 'react';
import { useAppStore } from './store';
import Layout from './components/Layout';
import ToastBridge from './components/ToastBridge';
import Dashboard from './pages/Dashboard';
import Chat from './pages/Chat';
import Sessions from './pages/Sessions';
import Channels from './pages/Channels';
import MCPServers from './pages/MCPServers';
import Settings from './pages/Settings';
import Skills from './pages/Skills';
import Logs from './pages/Logs';
import Bots from './pages/Bots';
import Agents from './pages/Agents';
import Plans from './pages/Plans';
import Memory from './pages/Memory';
import BotProfile from './pages/BotProfile';
import Cron from './pages/Cron';
import Health from './pages/Health';
import Workspace from './pages/Workspace';
import Activity from './pages/Activity';
import Queue from './pages/Queue';

function resolveIsDark(theme: 'light' | 'dark' | 'system'): boolean {
  if (theme === 'dark') return true;
  if (theme === 'light') return false;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function AppRoutes() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-gray-100">
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/chat/:sessionKey" element={<Chat />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/channels" element={<Channels />} />
          <Route path="/cron" element={<Cron />} />
          <Route path="/health" element={<Health />} />
          <Route path="/workspace" element={<Workspace />} />
          <Route path="/mcp" element={<MCPServers />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/agents" element={<Agents />} />
          <Route path="/plans" element={<Plans />} />
          <Route path="/skills" element={<Skills />} />
          <Route path="/memory" element={<Memory />} />
          <Route path="/bot-profile" element={<BotProfile />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/activity" element={<Activity />} />
          <Route path="/queue" element={<Queue />} />
        </Routes>
      </Layout>
      <ToastBridge />
    </div>
  );
}

function App() {
  const { theme } = useAppStore();
  const [isDark, setIsDark] = useState(() => resolveIsDark(theme));

  useEffect(() => {
    setIsDark(resolveIsDark(theme));
    if (theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      const handler = () => setIsDark(mq.matches);
      mq.addEventListener('change', handler);
      return () => mq.removeEventListener('change', handler);
    }
  }, [theme]);

  return (
    <ConfigProvider
      theme={{
        algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          colorPrimary: '#3b82f6',
          borderRadius: 10,
          fontFamily: '"Plus Jakarta Sans", Inter, system-ui, -apple-system, sans-serif',
          colorBgContainer: isDark ? undefined : '#ffffff',
          colorBgElevated: isDark ? undefined : '#ffffff',
        },
        components: {
          Card: {
            borderRadiusLG: 16,
            borderRadius: 12,
          },
          Button: {
            borderRadius: 10,
            controlHeight: 36,
          },
          Input: {
            borderRadius: 10,
            controlHeight: 40,
          },
          Select: {
            borderRadius: 10,
            controlHeight: 40,
          },
        },
      }}
    >
      <AntdApp>
        <AppRoutes />
      </AntdApp>
    </ConfigProvider>
  );
}

export default App;
