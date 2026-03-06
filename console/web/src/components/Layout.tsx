import { ReactNode, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, Button, Badge, Segmented } from 'antd';
import type { MenuProps } from 'antd';
import { useAppStore } from '../store';
import {
  LayoutDashboard,
  MessageSquare,
  FolderOpen,
  Smartphone,
  Plug,
  Settings,
  FileText,
  ChevronLeft,
  ChevronRight,
  Bot,
  Menu as MenuIcon,
  X,
  Cpu,
  Sun,
  Moon,
  Monitor,
} from 'lucide-react';

interface LayoutProps {
  children: ReactNode;
}

type NavItem = {
  path: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

type NavSection = {
  title: string;
  items: NavItem[];
};

const navSections: NavSection[] = [
  {
    title: 'Chat',
    items: [
      { path: '/dashboard', label: 'Overview', icon: LayoutDashboard },
      { path: '/chat', label: 'Chat', icon: MessageSquare },
    ],
  },
  {
    title: 'Control',
    items: [
      { path: '/channels', label: 'Channels', icon: Smartphone },
      { path: '/sessions', label: 'Sessions', icon: FolderOpen },
    ],
  },
  {
    title: 'Agent',
    items: [
      { path: '/mcp', label: 'MCP', icon: Plug },
      { path: '/logs', label: 'Logs', icon: FileText },
    ],
  },
  {
    title: 'Settings',
    items: [{ path: '/settings', label: 'Settings', icon: Settings }],
  },
];

export default function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const { sidebarCollapsed, setSidebarCollapsed, status, theme, setTheme } = useAppStore();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const selectedKey = '/' + (location.pathname.split('/')[1] || 'dashboard');

  const menuItems: MenuProps['items'] = navSections.map((section) => ({
    type: 'group',
    label: section.title,
    children: section.items.map((item) => {
      const Icon = item.icon;
      return {
        key: item.path,
        icon: <Icon className="w-4 h-4" />,
        label: (
          <Link to={item.path} onClick={() => setMobileMenuOpen(false)}>
            {item.label}
          </Link>
        ),
      };
    }),
  }));

  return (
    <div className="flex min-h-screen">
      {/* Mobile Menu Button */}
      <button
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        className="lg:hidden fixed top-3 left-3 z-50 p-2 rounded-lg bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 shadow-md"
      >
        {mobileMenuOpen ? <X className="w-5 h-5" /> : <MenuIcon className="w-5 h-5" />}
      </button>

      {/* Mobile Overlay */}
      {mobileMenuOpen && (
        <div
          className="lg:hidden fixed inset-0 bg-black/50 z-30"
          onClick={() => setMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`
          ${sidebarCollapsed ? 'w-20' : 'w-64'}
          ${mobileMenuOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
          fixed lg:relative z-40 h-screen
          bg-gradient-to-b from-white via-white to-gray-50 dark:from-gray-900 dark:via-gray-800 dark:to-gray-900
          border-r border-gray-200/50 dark:border-gray-700/50
          flex flex-col transition-all duration-300 ease-out
          shadow-[4px_0_24px_rgba(0,0,0,0.02)] dark:shadow-none
        `}
      >
        {/* Logo */}
        <div className="h-16 flex items-center px-4 border-b border-gray-200/50 dark:border-gray-700/50 bg-white/50 dark:bg-gray-800/50 backdrop-blur-sm">
          <div className="flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 shadow-lg shadow-primary-500/25">
            <Bot className="w-5 h-5 text-white" />
          </div>
          {!sidebarCollapsed && (
            <div className="ml-3 flex flex-col">
              <span className="font-bold text-lg bg-gradient-to-r from-gray-900 to-gray-600 dark:from-white dark:to-gray-300 bg-clip-text text-transparent">
                Nanobot
              </span>
              <span className="text-[10px] text-gray-400 -mt-0.5">AI Assistant</span>
            </div>
          )}
        </div>

        {/* Navigation using antd Menu */}
        <nav className="flex-1 overflow-y-auto py-2">
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            inlineCollapsed={sidebarCollapsed}
            items={menuItems}
            style={{ background: 'transparent', borderRight: 'none' }}
          />
        </nav>

        {/* Collapse Button - Desktop Only */}
        <div className="hidden lg:block p-3 border-t border-gray-200/50 dark:border-gray-700/50">
          <Button
            type="text"
            block
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            icon={
              sidebarCollapsed ? (
                <ChevronRight className="w-4 h-4" />
              ) : (
                <ChevronLeft className="w-4 h-4" />
              )
            }
          >
            {!sidebarCollapsed && 'Collapse'}
          </Button>
        </div>

        {/* Status Indicator */}
        {status && (
          <div className="p-4 border-t border-gray-200/50 dark:border-gray-700/50 bg-white/30 dark:bg-gray-800/30 backdrop-blur-sm">
            <div className="flex items-center gap-3 p-3 rounded-xl bg-gray-50 dark:bg-gray-700/30">
              <Badge
                status={status.running ? 'processing' : 'default'}
                color={status.running ? '#22c55e' : undefined}
              />
              {!sidebarCollapsed && (
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
                    {status.running ? 'Running' : 'Stopped'}
                  </p>
                  {status.model && (
                    <p className="text-[10px] text-gray-400 truncate">{status.model}</p>
                  )}
                </div>
              )}
              {!sidebarCollapsed && status.running && (
                <Cpu className="w-4 h-4 text-green-500" />
              )}
            </div>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0 overflow-auto">
        {/* Global Header */}
        <header className="sticky top-0 z-20 h-14 flex items-center justify-end px-4 lg:px-6 border-b border-gray-200/50 dark:border-gray-700/50 bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm">
          <Segmented
            value={theme}
            onChange={(val) => setTheme(val as 'light' | 'dark' | 'system')}
            options={[
              { value: 'light', icon: <Sun className="w-4 h-4" /> },
              { value: 'dark', icon: <Moon className="w-4 h-4" /> },
              { value: 'system', icon: <Monitor className="w-4 h-4" /> },
            ]}
          />
        </header>

        {children}
      </main>
    </div>
  );
}
