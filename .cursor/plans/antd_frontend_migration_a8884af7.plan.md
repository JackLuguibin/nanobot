---
name: Antd Frontend Migration
overview: Introduce Ant Design (antd) as the UI component library alongside Tailwind CSS. Replace hand-crafted buttons, forms, tables, modals, and navigation with antd components, and wire up antd's built-in dark/light theme algorithm to the existing Zustand theme state.
todos:
  - id: install-antd
    content: Install antd and @ant-design/icons in console/web
    status: completed
  - id: config-provider
    content: Wrap App.tsx with ConfigProvider and wire darkAlgorithm to Zustand theme state
    status: completed
  - id: layout-menu
    content: Migrate Layout.tsx sidebar/nav to antd Layout + Sider + Menu
    status: completed
  - id: toast-migration
    content: Remove Toast.tsx component; replace addToast calls with antd message/notification API
    status: completed
  - id: settings-form
    content: Migrate Settings.tsx to antd Form, Input, Select, InputNumber, Slider, Tabs, Switch
    status: completed
  - id: logs-table
    content: Migrate Logs.tsx to antd Table, Select, Input.Search, Statistic, Tag
    status: completed
  - id: sessions-table
    content: Migrate Sessions.tsx to antd Table, Input.Search, Popconfirm, Modal
    status: completed
  - id: dashboard-cards
    content: Migrate Dashboard.tsx to antd Card, Statistic, Button, Tag, Spin, Alert
    status: completed
  - id: channels-cards
    content: Migrate Channels.tsx to antd Card, Badge, Tag, Descriptions, Button
    status: completed
  - id: mcp-cards
    content: Migrate MCPServers.tsx to antd Card, Tag, Descriptions, Button
    status: completed
  - id: chat-ui
    content: Migrate Chat.tsx to antd Input, Button, Spin, Tag, Tooltip
    status: completed
isProject: false
---

# Antd Frontend Migration

## Strategy

Keep Tailwind for layout/spacing utilities. Replace interactive UI elements (buttons, inputs, forms, tables, menus, modals, tags, notifications) with antd components. Wire antd's `darkAlgorithm` to the existing `theme` state in the Zustand store.

## Key files to change

- `[console/web/package.json](console/web/package.json)` — add `antd` and `@ant-design/icons`
- `[console/web/src/App.tsx](console/web/src/App.tsx)` — wrap with `ConfigProvider`, compute `isDark` from store
- `[console/web/src/components/Layout.tsx](console/web/src/components/Layout.tsx)` — replace sidebar/nav with antd `Layout` + `Menu`
- `[console/web/src/components/Toast.tsx](console/web/src/components/Toast.tsx)` — replace with antd `message` / `notification` API
- `[console/web/src/pages/Dashboard.tsx](console/web/src/pages/Dashboard.tsx)` — `Card`, `Statistic`, `Button`, `Tag`, `Spin`, `Alert`
- `[console/web/src/pages/Sessions.tsx](console/web/src/pages/Sessions.tsx)` — `Table`, `Button`, `Input.Search`, `Popconfirm`, `Modal`
- `[console/web/src/pages/Channels.tsx](console/web/src/pages/Channels.tsx)` — `Card`, `Badge`, `Tag`, `Button`, `Descriptions`
- `[console/web/src/pages/MCPServers.tsx](console/web/src/pages/MCPServers.tsx)` — `Card`, `Tag`, `Descriptions`, `Button`
- `[console/web/src/pages/Settings.tsx](console/web/src/pages/Settings.tsx)` — `Form`, `Input`, `Select`, `InputNumber`, `Slider`, `Tabs`, `Switch`, `Radio.Group`
- `[console/web/src/pages/Logs.tsx](console/web/src/pages/Logs.tsx)` — `Table`, `Select`, `Input`, `Statistic`, `Tag`
- `[console/web/src/pages/Chat.tsx](console/web/src/pages/Chat.tsx)` — `Input`, `Button`, `Spin`, `Tag`, `Tooltip`

## Theme integration

In `App.tsx`, read `theme` from the store and derive `isDark`:

```tsx
import { ConfigProvider, theme as antdTheme } from 'antd';
// inside App():
const { theme } = useAppStore();
const [isDark, setIsDark] = useState(() => resolveIsDark(theme));
// keep in sync with store changes + system events

<ConfigProvider theme={{ algorithm: isDark ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm }}>
  ...
</ConfigProvider>
```

Continue to set the `dark` class on `documentElement` (from the store) so Tailwind dark utilities still work.

## Component mapping

- Custom buttons → `Button` (type="primary" / "default" / "text" / "link" / "dashed")
- Tailwind badges/pills → `Tag` with `color`
- Hand-rolled tables → `Table` with typed `columns`
- Inline status dots → `Badge status="success|error|default"`
- `confirm()` → `Modal.confirm()` or `Popconfirm`
- `Toast.tsx` → removed; replaced by `message.success/error()` / `notification` calls in each page
- Custom form fields → `Form.Item` + `Input` / `Select` / `InputNumber` / `Slider` / `Switch`
- Sidebar nav → antd `Menu` with `items` inside antd `Sider`
- Header → antd `Header`

## What stays as Tailwind

- Page-level spacing and grid (`p-6`, `grid grid-cols-*`, `gap-*`)
- Flex layout utilities
- Gradient text styles in `index.css`
- Custom scrollbar styles

## Dependency install

```bash
cd console/web
npm install antd @ant-design/icons
```

