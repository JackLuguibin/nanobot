---
name: OpenAkita 对比与功能补充
overview: 基于 OpenAkita 与 nanobot 的对比研究，列出 nanobot 已有能力与缺口，并给出可补充的功能方向与实现优先级建议。
todos: []
isProject: false
---

# OpenAkita 与 nanobot 对比研究与功能补充建议

## 一、对比总览


| 维度    | OpenAkita                                                   | nanobot 现状                                                                     |
| ----- | ----------------------------------------------------------- | ------------------------------------------------------------------------------ |
| 定位    | 全功能多智能体助手，GUI 5 分钟上手                                        | 极简个人助手，研究向、可扩展                                                                 |
| 推理引擎  | 显式 ReAct（Think→Act→Observe）+ checkpoint/回滚                  | 单轮 Agent 循环（context→LLM→tools→reply），无显式 ReAct 阶段与回滚                           |
| 多智能体  | AgentOrchestrator + 多专业 Agent 并行/交接/故障转移 + 可视化 Dashboard    | 主 Agent + SubagentManager（后台 spawn 单任务），Console 的 Agents 为「配置档」非编排             |
| 计划模式  | 任务自动分解、分步追踪、进度条、失败回滚                                        | 无；仅有 loop 内提示 "break into smaller steps"                                       |
| 工具数量  | 89+（16 类：Shell/Files/Browser/Desktop/Search/Scheduler/MCP…） | 约 10+ 内置（文件/exec/web/cron/message/spawn/MCP），依赖 MCP 与 skills 扩展                |
| 技能生态  | Skill Marketplace 搜索 + 一键安装 + AI 生成技能                       | ClawHub skill + Console 从 registry 安装，无内置「AI 生成技能」                             |
| 渠道    | 6 个 IM（Telegram/Feishu/WeCom/钉钉/QQ/OneBot）                  | 11 个（含 Telegram/Feishu/钉钉/QQ/Wecom/Slack/Discord/WhatsApp/Email/Matrix/Mochat） |
| 记忆    | 三层（Working + Core + Dynamic）+ 7 类记忆 + 向量检索                  | 两层（MEMORY.md + HISTORY.md）+ grep，无向量/语义检索层                                     |
| 人设/人格 | 8 种 Persona 预设                                              | 无统一 Persona 层，仅 SOUL.md 系统提示                                                   |
| 主动能力  | 主动引擎：问候/跟进/闲谈/晚安等                                           | Heartbeat：HEARTBEAT.md 周期任务，无问候/闲谈等策略                                          |
| 自进化   | 每日自检、失败根因分析、自动生成/安装技能                                       | 无                                                                              |
| 安全与治理 | POLICIES.yaml、危险操作需用户确认、资源预算                                | exec 黑名单/可选白名单、restrictToWorkspace、allowFrom；无统一 POLICIES、无危险操作确认              |
| 前端形态  | Desktop（Tauri）+ Web + Mobile（Capacitor）                     | 仅 Web Console（FastAPI + React）                                                 |
| 可观测   | 12 类 trace span、全链 token 统计                                 | Dashboard 有 token/用量统计，无多 span 追踪                                              |


---

## 二、nanobot 已有且与 OpenAkita 可比的能力

- **渠道**：IM 数量更多（含 Matrix、Email、Slack、Discord、WhatsApp 等），配置在 [nanobot/channels/](nanobot/channels/)。
- **多 Bot 实例**：BotRegistry + Console 多 Bot 切换，每个 Bot 独立 config/workspace（[console/server/bot_registry.py](console/server/bot_registry.py)）。
- **Agent 配置**：Console [Agents 页](console/web/src/pages/Agents.tsx) 支持多「Agent」配置（名称、模型、技能、协作者等），当前用于配置档而非编排路由。
- **思考模式**：`reasoning_effort` / `reasoning_content` 已贯通 provider/context/前端（[nanobot/providers/base.py](nanobot/providers/base.py)、[console/web/src/pages/Settings.tsx](console/web/src/pages/Settings.tsx)）。
- **记忆**：两层记忆 + MemoryConsolidator（[nanobot/agent/memory.py](nanobot/agent/memory.py)），Memory 页可查看/管理。
- **安全**：exec 黑名单 + 可选 allowlist、restrictToWorkspace（[nanobot/agent/tools/shell.py](nanobot/agent/tools/shell.py)、config）。
- **技能**：ClawHub skill、技能目录、Console 从 registry 安装（[console/server/extension/skills_registry.py](console/server/extension/skills_registry.py)）。
- **定时与主动**：Cron + Heartbeat（HEARTBEAT.md），无「问候/闲谈」策略。

---

## 三、建议补充的功能方向（按优先级）

### 高优先级（与核心体验强相关）

1. **计划模式（Plan Mode）**
  - **缺口**：OpenAkita 可将复杂任务分解为步骤、分步执行并追踪、失败回滚。
  - **建议**：在 extension 层增加「计划执行器」：对高复杂度请求先由 LLM 输出步骤列表（或结构化 plan），再按步执行并在 Console 展示进度（步骤列表 + 当前步/状态）。可先做「单 Bot 内顺序执行 + 进度 API」，不做自动回滚也可接受。
  - **涉及**：`console/server/extension/` 新模块、AgentLoop 或 Session 的扩展调用、Console 新页面或 Chat 内嵌步骤 UI、可选 plan 相关 API。
2. **显式 ReAct 与简单回滚**
  - **缺口**：OpenAkita 的 Think→Act→Observe 与 checkpoint/回滚。
  - **建议**：在保持现有 loop 的前提下，在 context 或 loop 中显式区分「思考 / 行动 / 观察」阶段（例如在 prompt 或消息结构中标明），并在一轮中保留「上一步观察」的 checkpoint；若本步失败可重试或回退到上一 checkpoint 再换策略。实现可轻量（如仅「上一轮 tool 结果」快照 + 重试一次），不追求完整 ReAct 框架。
3. **危险操作确认（Safety & Governance）**
  - **缺口**：OpenAkita 的 POLICIES.yaml 与危险操作需用户确认。
  - **建议**：在 **不修改 nanobot 核心** 的前提下，在 console extension 层做：
    - 定义「危险操作」列表（如 exec 某些命令、删除文件、写系统路径等），与现有 exec deny/allow 配合；
    - 当 Agent 要执行危险操作时，通过 MessageTool 或专用通道向用户发送「待确认」请求，WebSocket 推送到前端，用户确认/拒绝后再继续。
  - 可选：在 workspace 或 config 目录支持类似 `POLICIES.yaml` 的配置（由 console 读取），驱动「哪些算危险、是否必须确认」。

### 中优先级（体验与可观测）

1. **三层记忆与向量检索**
  - **缺口**：OpenAkita 的 Working + Core + Dynamic 与向量检索。
  - **建议**：在现有 MEMORY.md + HISTORY.md 之上增加「动态检索层」：对话前用当前 query 做向量检索（或关键词+时间）从 HISTORY/记忆片段中取回相关条目，注入 context。需要 embedding 与向量存储（可在 extension 中实现，避免改 nanobot 核心）。
2. **多智能体编排（轻量）**
  - **缺口**：OpenAkita 的 AgentOrchestrator 与多 Agent 并行/交接。
  - **建议**：利用 Console 已有「多 Agent 配置」，在 extension 中实现「路由/编排层」：根据用户意图或 topic 选择不同 Agent 配置（不同 model/skills），或对子任务 spawn 到不同配置的 Agent，结果再汇总。先做「单 Bot 内多配置路由 + 可选 spawn」，不做复杂 DAG。
3. **资源与运行时监督**
  - **缺口**：OpenAkita 的 token/成本/时长/迭代/工具调用预算与 tool thrashing 检测。
  - **建议**：在 AgentLoop 外层或 extension 中增加「运行预算」：单次会话或单任务的 max_tokens / max_tool_calls / max_duration；超限则中止并返回提示。可选：检测短时间大量同类 tool 调用并告警或限流。

### 低优先级（差异化与生态）

1. **主动引擎策略**
  - **缺口**：OpenAkita 的问候、任务跟进、闲谈、晚安等。
  - **建议**：在 Heartbeat 或独立「Proactive 策略」模块中，按时间/空闲/上次对话结果触发固定任务（如「发一句问候」「总结待办」），仍通过现有 channel 回复；策略可配置（开关、频率）。
2. **Persona 预设**
  - **缺口**：OpenAkita 的 8 种 Persona。
  - **建议**：在 config 或 Console 中增加 `persona` 字段，可选若干预设（如 default/tech/assistant 等），映射到不同 SOUL 片段或 system prompt 追加内容，不改 nanobot 核心。
3. **可观测与 Trace**
  - **缺口**：OpenAkita 的 12 类 span 与全链追踪。
  - **建议**：在现有 token 统计基础上，为「会话/轮次/工具调用/子 agent」打 span（如 trace_id + span_id），写入日志或轻量存储，Console 提供「单次对话 trace 视图」与简单 token 分布。
4. **Skill 发现与 AI 生成**
  - **缺口**：OpenAkita 的 Skill Marketplace 与 AI 生成技能。
    - **建议**：技能发现已部分具备（ClawHub + registry）；「AI 生成技能」可在 Console 或 CLI 中提供「用自然语言描述 → 生成 SKILL.md + 脚本骨架」的流程，由 LLM 生成后再走现有安装流程。

---

## 四、架构约束（与现有规则一致）

- **不修改 nanobot 核心**：所有新逻辑放在 `console/server/extension/` 或通过扩展/包装调用 nanobot。
- **API 与扩展分离**：新能力在 extension 实现，通过 [console/server/api/](console/server/api/) 暴露 REST/WebSocket。
- **前端**：新 UI 在 [console/web/src/pages/](console/web/src/pages/) 或现有页内组件，继续使用 antd + Tailwind。

---

## 五、建议实施顺序（若分阶段做）

1. **Phase 1**：危险操作确认（安全）+ 计划模式（步骤展示与进度 API）。
2. **Phase 2**：显式 ReAct/checkpoint 与轻量回滚 + 资源预算与简单运行时监督。
3. **Phase 3**：三层记忆/向量检索 + 多 Agent 配置路由/编排。
4. **Phase 4**：主动策略、Persona、Trace 视图、Skill AI 生成（按需）。

以上顺序可根据「安全优先」或「体验优先」调整；若资源有限，可只做 Phase 1 与 2 中的若干项。