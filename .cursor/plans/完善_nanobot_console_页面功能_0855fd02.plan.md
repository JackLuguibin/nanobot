---
name: 完善 nanobot console 页面功能
overview: 全面改进 nanobot console 的前端页面，参考 CoPaw 设计思路，增强用户体验和功能完整性。主要改进 Dashboard、Chat、Sessions、Channels、MCPServers、Settings、Logs 等页面，并完善 API 客户端。
todos:
  - id: api-enhancement
    content: 增强 API 客户端 - 添加流式响应和批量操作
    status: completed
  - id: dashboard-enhancement
    content: 改进 Dashboard - 添加快速操作和活动流
    status: completed
  - id: chat-enhancement
    content: 改进 Chat 页面 - 流式响应、工具调用可视化、代码高亮
    status: completed
  - id: sessions-enhancement
    content: 改进 Sessions 页面 - 批量操作、详情预览
    status: completed
  - id: channels-enhancement
    content: 改进 Channels 页面 - 详情面板、刷新按钮
    status: completed
  - id: mcp-enhancement
    content: 改进 MCPServers 页面 - 测试连接、更多详情
    status: completed
  - id: settings-enhancement
    content: 改进 Settings 页面 - 完善各标签页内容
    status: completed
  - id: logs-enhancement
    content: 改进 Logs 页面 - 展开折叠、搜索过滤
    status: completed
  - id: common-components
    content: 添加通用组件 - Toast 通知、统一加载/错误状态
    status: completed
isProject: false
---

## 改进计划

### 第一阶段：API 客户端增强 ([console/web/src/api/client.ts](console/web/src/api/client.ts))

1. 添加流式响应支持 (SSE)
2. 添加批量操作 API
3. 添加连接测试相关 API

### 第二阶段：Dashboard 增强 ([console/web/src/pages/Dashboard.tsx](console/web/src/pages/Dashboard.tsx))

1. 添加快速操作按钮（重启机器人、停止当前任务）
2. 添加最近活动流/消息预览
3. 添加 CPU/内存使用率占位
4. 优化响应式布局

### 第三阶段：Chat 页面增强 ([console/web/src/pages/Chat.tsx](console/web/src/pages/Chat.tsx))

1. 真正的流式响应实现 (SSE)
2. 添加工具调用可视化展示
3. 增强 Markdown 渲染（代码高亮、语法高亮）
4. 添加停止生成按钮
5. 添加消息复制功能
6. 改进空状态展示

### 第四阶段：Sessions 页面增强 ([console/web/src/pages/Sessions.tsx](console/web/src/pages/Sessions.tsx))

1. 添加批量删除功能
2. 添加会话详情预览（悬停/点击展开）
3. 改进空状态和加载状态
4. 添加排序选项（时间、消息数）

### 第五阶段：Channels 页面增强 ([console/web/src/pages/Channels.tsx](console/web/src/pages/Channels.tsx))

1. 添加渠道详情面板
2. 添加连接状态指示器
3. 添加刷新状态按钮
4. 改进配置展示

### 第六阶段：MCPServers 页面增强 ([console/web/src/pages/MCPServers.tsx](console/web/src/pages/MCPServers.tsx))

1. 添加连接测试按钮
2. 显示更多服务器详情
3. 添加刷新按钮
4. 改进错误展示

### 第七阶段：Settings 页面增强 ([console/web/src/pages/Settings.tsx](console/web/src/pages/Settings.tsx))

1. 完善 Providers 标签页 - 实际显示已配置的 providers
2. 完善 Tools 标签页 - 显示已配置的 MCP servers
3. 完善 Channels 标签页 - 显示已配置的 channels
4. 添加导入/导出配置功能

### 第八阶段：Logs 页面增强 ([console/web/src/pages/Logs.tsx](console/web/src/pages/Logs.tsx))

1. 改进 JSON 展开/折叠
2. 添加日志搜索功能
3. 添加时间范围过滤
4. 改进结果展示格式

### 第九阶段：通用改进

1. 统一加载状态和错误处理
2. 添加 Toast 通知组件
3. 改进响应式设计
4. 添加动画过渡效果