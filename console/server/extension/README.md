# Console Extension 扩展模块

本目录包含对 nanobot 核心功能的扩展和补丁。所有对 nanobot 核心的定制都应放在这里，保持 nanobot 本身的独立性。

## 模块说明

| 模块 | 说明 |
|------|------|
| `cli.py` | Console CLI 扩展，提供启动命令实现（run_console_server、run_full_stack 等） |
| `skills.py` | Skills 管理扩展，提供 PatchedContextBuilder、技能列表与内容管理 |
| `skills_registry.py` | **Skills Registry**：从远程 JSON 拉取技能列表，支持 search/install |
| `usage.py` | **Token 使用量追踪**：包装 LLM provider，累积 token 用量与成本，供 Dashboard 展示 |
| `alerts.py` | **Smart Alerts**：成本超阈值、Cron 逾期、MCP/通道异常告警 |
| `health.py` | **Health Audit**：Bootstrap 文件、MCP 配置、通道等健康检查 |
| `activity.py` | **Activity 持久化**：tool_call 日志持久化到 activity.json |
| `cron_history.py` | **Cron 执行历史**：记录每次 Cron 执行到 history.json |
| `plans.py` | **Plans 看板**：Plans 看板数据持久化到 plans.json，供 Agent 下 Plans 页面使用 |
| `message_source.py` | **消息来源**：为 session 消息增加 `source` 字段（user/main_agent/sub_agent/tool_call），供前端只展示用户与主 Agent |
| `subagent_events.py` | **子 Agent 事件**：Patch SubagentManager，向前端 SSE 推送 subagent_start/subagent_done |

## usage.py 实现说明

- **UsageTrackingProvider**：包装任意 `LLMProvider`，在 `chat()` 返回后从 response.usage 累积并持久化到 JSON 文件
- **get_usage_today(bot_id)**：返回指定 bot 当日 token 使用量
- **get_usage_history(bot_id, days)**：返回最近 N 天每日使用量，供 Dashboard 柱状图展示
- **存储路径**：每个 bot 的 usage 存储在自身 config 目录下 `{config_path.parent}/usage.json`，结构为 `{date: {prompt_tokens, completion_tokens, total_tokens}}`，不放在公共区域
- 由 `main.py` 在创建 AgentLoop 前包装 provider，由 `state.py` 的 `get_status()` 调用 `get_usage_today` 返回给前端
