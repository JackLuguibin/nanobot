# Nanobot 后端管理层设计方案

> 设计原则：nanobot 核心不可修改，前端功能不变，后端通过扩展机制与 nanobot 交互
>
> **核心约束：严格保持各层独立性，Gateway 层不受后端管理层影响**

---

## 目录

1. [设计背景与核心约束](#1-设计背景与核心约束)
2. [层间隔离架构](#2-层间隔离架构)
3. [Gateway 层独立性](#3-gateway-层独立性)
4. [核心组件设计](#4-核心组件设计)
5. [数据流设计](#5-数据流设计)
6. [API 设计](#6-api-设计)
7. [配置管理](#7-配置管理)
8. [改造实施计划](#8-改造实施计划)

---

## 1. 设计背景与核心约束

### 1.1 设计目标

| 目标 | 约束级别 | 说明 |
|------|----------|------|
| nanobot 核心独立 | **硬约束** | `nanobot/` 目录源码绝对不可修改 |
| 前端功能不变 | **硬约束** | 现有 API 接口 100% 兼容，无需前端改动 |
| Gateway 层独立 | **硬约束** | nanobot Gateway 通信不受后端管理层影响 |
| 后端可演进 | **软约束** | 后端管理层可独立重构和扩展 |

### 1.2 当前问题

| 问题 | 影响范围 | 严重性 |
|------|----------|--------|
| 状态分散 | 后端内部 | 中 |
| API 碎片化 | 后端内部 | 中 |
| 配置耦合 | 后端 + nanobot | 高 |
| Gateway 依赖后端状态 | Gateway + 后端 | 高 |
| nanobot 直接调用 | nanobot | 严重 |

### 1.3 核心约束：层间隔离原则

```mermaid
flowchart TB
    subgraph Inviolable["不可违反的隔离边界"]
        direction TB
        F["Frontend<br/>(前端)"]
        B["Backend<br/>(后端管理层)"]
        G["Gateway<br/>(nanobot Gateway)"]
        N["Nanobot Core<br/>(不可修改)"]
    end
    
    F -->|"HTTP/WebSocket"| B
    B -.->|"配置驱动<br/>无直接调用"| N
    G -.->|"直接通信"| N
    B -.-|"只读观察<br/>配置下发"| G
    
    style F fill:#e1f5ff,stroke:#01579b
    style B fill:#fff3e0,stroke:#e65100
    style G fill:#e8f5e9,stroke:#2e7d32
    style N fill:#fce4ec,stroke:#c2185b
    style Inviolable fill:none,stroke:#d32f2f,stroke-width:3px
```

### 1.4 依赖方向约束

```mermaid
flowchart LR
    direction RL
    
    subgraph Layers["依赖方向 (从外到内)"]
        Frontend["Frontend"]
        Backend["Backend Facade"]
        Extension["Extension"]
        Gateway["Gateway Adapter"]
        Nanobot["Nanobot Core"]
    end
    
    Frontend --> Backend
    Backend --> Extension
    Extension -.->|"仅读取<br/>无修改"| Nanobot
    Gateway -.->|"直接调用"| Nanobot
    Backend -.->|"仅读取状态<br/>无直接调用"| Gateway
    
    style Frontend fill:#e1f5ff
    style Backend fill:#fff3e0
    style Extension fill:#fff8e1
    style Gateway fill:#e8f5e9
    style Nanobot fill:#fce4ec
```

---

## 2. 层间隔离架构

### 2.1 六层架构模型

```mermaid
flowchart TB
    subgraph L1["第一层：前端层 (Frontend)"]
        UI["页面组件"]
        Store["状态管理"]
        WSClient["WebSocket 客户端"]
    end
    
    subgraph L2["第二层：API 网关层 (API Gateway)"]
        Router["路由分发"]
        Auth["认证/鉴权"]
        Validator["请求验证"]
        RateLimit["限流"]
    end
    
    subgraph L3["第三层：后端管理层 (Management Facade)"]
        StateFacade["StateFacade<br/>统一状态"]
        
        subgraph Facades["业务管理器"]
            AgentF["AgentFacade"]
            ChannelF["ChannelFacade"]
            SessionF["SessionFacade"]
            CronF["CronFacade"]
        end
        
        StateFacade --> Facades
    end
    
    subgraph L4["第四层：扩展层 (Extension)"]
        ConfigBridge["配置桥接"]
        EventBridge["事件桥接"]
        Patched["补丁组件"]
    end
    
    subgraph L5["第五层：Gateway 适配层 (Gateway Adapter)"]
        GatewayBridge["Gateway 适配器"]
        GatewayState["Gateway 状态"
        GatewayConfig["配置下发"]
    end
    
    subgraph L6["第六层：nanobot 核心 (Nanobot Core) - 不可修改"]
        AgentLoop["AgentLoop"]
        ChannelMgr["ChannelManager"]
        SessionMgr["SessionManager"]
        Gateway["Gateway"]
        ConfigCore["Config"]
    end
    
    L1 --> L2
    L2 --> L3
    L3 --> L4
    L4 -.->|"仅读配置<br/>无直接调用"| L6
    L5 -.->|"直接通信"| L6
    L3 -.->|"只读观察"| L5
    
    L1 fill:#e1f5ff
    L2 fill:#e3f2fd
    L3 fill:#fff3e0
    L4 fill:#fff8e1
    L5 fill:#e8f5e9
    L6 fill:#fce4ec
```

### 2.2 层间通信协议

```mermaid
classDiagram
    class IStateObserver {
        <<interface>>
        +on_state_change(event: StateEvent)
        +on_health_change(event: HealthEvent)
    }
    
    class IConfigDriver {
        <<interface>>
        +load_config() Config
        +save_config(config: Config)
        +watch_config(callback)
    }
    
    class IGatewayBridge {
        <<interface>>
        +get_gateway_status() GatewayStatus
        +send_command(cmd: GatewayCommand)
        +subscribe_events(callback)
    }
    
    class IEventPublisher {
        <<interface>>
        +publish(event: FacadeEvent)
        +subscribe(topic: str, callback)
    }
    
    StateFacade ..> IStateObserver
    StateFacade ..> IConfigDriver
    GatewayAdapter ..> IGatewayBridge
    Extension ..> IConfigDriver
    EventBus ..> IEventPublisher
```

### 2.3 目录结构

```mermaid
graph TD
    subgraph Console["console/server/"]
        
        subgraph Facade["facade/ (新增)"]
            Base["base.py<br/>基础接口定义"]
            
            subgraph FacadeCore["核心 Facade"]
                AgentF["agent/manager.py"]
                ChannelF["channel/manager.py"]
                SessionF["session/manager.py"]
                CronF["cron/manager.py"]
                ProviderF["provider/manager.py"]
                SkillF["skill/manager.py"]
            end
            
            subgraph FacadeState["状态管理"]
                StateMgr["state/manager.py"]
                StateWatcher["state/watcher.py"]
            end
            
            subgraph FacadeConfig["配置管理"]
                ConfigLoader["config/loader.py"]
                ConfigValidator["config/validator.py"]
                ConfigDiff["config/diff.py"]
            end
            
            Base --> FacadeCore
            Base --> FacadeState
            Base --> FacadeConfig
            StateMgr --> FacadeCore
        end
        
        subgraph ExtensionRefactor["extension/ (重构 - 仅适配)"]
            ConfigBridge["config_bridge.py<br/>配置桥接器"]
            EventBridge["event_bridge.py<br/>事件桥接"]
            GatewayState["gateway_state.py<br/>Gateway 状态观察"]
        end
        
        subgraph Gateway["gateway/ (新增 - Gateway 适配)"]
            GatewayAdapter["adapter.py<br/>Gateway 适配器"]
            GatewayCommands["commands.py<br/>命令定义"]
            GatewayStatus["status.py<br/>状态映射"]
        end
        
        subgraph APIRefactor["api/ (最小改动)"]
            ExistingAPI["现有端点<br/>(保持不变)"]
        end
        
        subgraph WebsocketRefactor["websocket/ (适配 Facade)"]
            WSHandler["handler.py"]
            RoomMgr["rooms.py"]
        end
        
        Facade --> ExtensionRefactor
        ExtensionRefactor -.->|"仅读取"| NanobotCore
        Gateway -.->|"直接通信"| NanobotCore
        Facade -.->|"只读观察"| Gateway
        APIRefactor --> Facade
    end
    
    subgraph NanobotCore["nanobot/ (绝对不可修改)"]
        AgentLoop["agent/loop.py"]
        ChannelMgr["channels/manager.py"]
        GatewayCore["gateway/"]
        ConfigCore["config/"]
        SessionMgr["session/"]
    end
    
    FacadeCore -.->|"导入 nanobot<br/>但仅调用公开 API"| AgentLoop
    GatewayAdapter -.->|"直接导入调用"| GatewayCore
```

---

## 3. Gateway 层独立性

### 3.1 Gateway 核心地位

```mermaid
flowchart TB
    subgraph Nanobot["nanobot 内部"]
        Gateway["Gateway<br/>(消息网关)"]
        AgentLoop["AgentLoop<br/>(Agent 循环)"]
        MessageBus["MessageBus<br/>(消息总线)"]
        Channels["Channels<br/>(多平台通道)"]
    end
    
    Gateway --> AgentLoop
    Gateway --> MessageBus
    MessageBus --> Channels
    AgentLoop --> MessageBus
    
    style Gateway fill:#e8f5e9,stroke:#2e7d32,stroke-width:3px
    style Nanobot fill:#fce4ec,stroke:#c2185b
```

### 3.2 Gateway 隔离策略

```mermaid
flowchart TB
    subgraph Before["重构前 (问题)"]
        B1["后端直接操作 Gateway 状态"]
        B2["后端直接调用 Gateway 方法"]
        B3["Gateway 依赖后端状态"]
    end
    
    subgraph After["重构后 (隔离)"]
        A1["Gateway 完全自主运行"]
        A2["后端仅通过配置影响 Gateway"]
        A3["后端仅观察 Gateway 状态"]
    end
    
    B1 & B2 & B3 -.x."有问题".-> A1 & A2 & A3
```

### 3.3 Gateway 适配器设计

```mermaid
classDiagram
    class IGatewayAdapter {
        <<interface>>
        +get_status() GatewayStatus
        +is_running() bool
        +get_stats() GatewayStats
    }
    
    class GatewayAdapter {
        +_gateway: Gateway
        +get_status() GatewayStatus
        +is_running() bool
        +get_stats() GatewayStats
        +subscribe_events(callback)
    }
    
    class GatewayBridge {
        +_adapter: IGatewayAdapter
        +_status_cache: dict
        +_subscribers: list
        +get_cached_status() GatewayStatus
        +refresh_status() GatewayStatus
        +watch_status(callback)
    }
    
    class Facade {
        +_gateway_bridge: GatewayBridge
        +get_gateway_status() GatewayStatus
        +_on_gateway_event(event)
    }
    
    GatewayAdapter ..|> IGatewayAdapter
    GatewayBridge --> IGatewayAdapter
    Facade --> GatewayBridge
    
    note for GatewayAdapter "仅读取，不修改<br/>与 nanobot Gateway 直接通信"
    note for GatewayBridge "状态缓存和事件转发"
    note for Facade "仅通过 GatewayBridge 观察状态"
```

### 3.4 Gateway 事件订阅

```mermaid
flowchart TB
    subgraph Gateway["Gateway (nanobot)"]
        G1["事件源<br/>(连接/断开/消息)"]
    end
    
    subgraph Adapter["GatewayAdapter"]
        A1["事件监听"]
        A2["状态缓存"]
        A3["事件转换"]
    end
    
    subgraph Bridge["GatewayBridge"]
        B1["事件分发"]
        B2["订阅管理"]
    end
    
    subgraph Consumers["消费者"]
        C1["StateFacade"]
        C2["WebSocket"]
        C3["告警系统"]
    end
    
    G1 --> A1
    A1 --> A2
    A2 --> A3
    A3 --> B1
    B1 --> C1
    B1 --> C2
    B1 --> C3
    
    style G1 fill:#e8f5e9,stroke:#2e7d32
    style C1 fill:#fff3e0,stroke:#e65100
    style C2 fill:#e1f5ff,stroke:#01579b
    style C3 fill:#f3e5f5,stroke:#7b1fa2
```

---

## 4. 核心组件设计

### 4.1 后端管理层组件

```mermaid
classDiagram
    class BaseManager~T~ {
        <<abstract>>
        +bot_id: str
        +_lock: asyncio.Lock
        +_subscribers: List~callable~
        +list() List~T~
        +get(identifier: str) Optional~T~
        +create(data: Dict) OperationResult
        +update(identifier: str, data: Dict) OperationResult
        +delete(identifier: str) OperationResult
        +start(identifier: str) OperationResult
        +stop(identifier: str) OperationResult
        +health_check() HealthCheckResult
        +subscribe(callback: callable)
        +notify(event: FacadeEvent)
    }
    
    class AgentFacade {
        +_agent_loop: AgentLoop
        +_config_loader: IConfigDriver
        +list() List~AgentInfo~
        +update(identifier: str, data: Dict) OperationResult
        +set_routing(rules: List) OperationResult
        +health_check() HealthCheckResult
    }
    
    class ChannelFacade {
        +_channel_manager: ChannelManager
        +_config_loader: IConfigDriver
        +list() List~ChannelInfo~
        +update(identifier: str, data: Dict) OperationResult
        +start(identifier: str) OperationResult
        +stop(identifier: str) OperationResult
        +health_check() HealthCheckResult
    }
    
    class SessionFacade {
        +_session_manager: SessionManager
        +list() List~SessionInfo~
        +get(identifier: str) Optional~SessionInfo~
        +delete(identifier: str) OperationResult
    }
    
    class CronFacade {
        +_cron_service: CronService
        +list() List~CronJobInfo~
        +create(data: Dict) OperationResult
        +update(identifier: str, data: Dict) OperationResult
        +delete(identifier: str) OperationResult
        +run(identifier: str) OperationResult
        +health_check() HealthCheckResult
    }
    
    class StateFacade {
        +_agent: AgentFacade
        +_channel: ChannelFacade
        +_session: SessionFacade
        +_cron: CronFacade
        +_gateway_bridge: GatewayBridge
        +get_unified_status() UnifiedStatus
        +execute_operation() OperationResult
        +watch_changes(callback: callable)
    }
    
    BaseManager <|-- AgentFacade
    BaseManager <|-- ChannelFacade
    BaseManager <|-- SessionFacade
    BaseManager <|-- CronFacade
    StateFacade --> AgentFacade
    StateFacade --> ChannelFacade
    StateFacade --> SessionFacade
    StateFacade --> CronFacade
    StateFacade --> GatewayBridge
    
    note for AgentFacade "nanobot 交互：仅通过配置变更"
    note for ChannelFacade "nanobot 交互：仅通过配置变更"
    note for StateFacade "统一状态聚合，不直接操作 nanobot"
```

### 4.2 配置驱动交互

```mermaid
sequenceDiagram
    participant Frontend
    participant API
    participant Facade
    participant ConfigMgr
    participant Nanobot
    
    Frontend->>API: PUT /config/channels/telegram
    API->>Facade: update("telegram", config)
    Facade->>ConfigMgr: calculate_diff(old, new)
    Facade->>ConfigMgr: validate(diff)
    Facade->>ConfigMgr: backup()
    Facade->>ConfigMgr: save(diff)
    
    ConfigMgr->>Nanobot: 配置变更通知
    Nanobot-->>ConfigMgr: 重新加载配置
    Nanobot->>Nanobot: 应用新配置
    
    ConfigMgr-->>Facade: save_complete
    Facade-->>API: OperationResult
    API-->>Frontend: {success: true}
    
    Note over Facade,Nanobot: Facade 仅修改配置文件<br/>nanobot 自行读取和应用配置
```

### 4.3 扩展层职责

```mermaid
flowchart TB
    subgraph ExtensionLayer["Extension Layer (扩展层)"]
        
        subgraph Adapters["适配器"]
            ConfigBridge["ConfigBridge<br/>配置桥接"]
            EventBridge["EventBridge<br/>事件桥接"]
            UsageTracker["UsageTracker<br/>使用量追踪"]
        end
        
        subgraph Patches["补丁 (向后兼容)"]
            MessageSource["message_source.py"]
            SubagentEvents["subagent_events.py"]
            SkillsPatch["skills.py"]
        end
        
        subgraph AdaptersForFacade["为 Facade 提供适配"]
            BotStateAdapter["BotStateAdapter<br/>BotState 适配"]
            ConfigAdapter["ConfigAdapter<br/>配置格式适配"]
        end
        
        ConfigBridge -.->|"读写"| NanobotConfig
        EventBridge -.->|"订阅"| NanobotEvents
        UsageTracker -.->|"包装"| NanobotProvider
        
        ConfigAdapter --> ConfigBridge
        BotStateAdapter --> Patches
    end
    
    subgraph NanobotCore["nanobot (不可修改)"]
        NanobotConfig["Config"]
        NanobotEvents["Event System"]
        NanobotProvider["LLMProvider"]
    end
    
    AdaptersForFacade --> Adapters
    style Adapters fill:#fff8e1,stroke:#ff8f00
    style Patches fill:#fff8e1,stroke:#ff8f00
    style AdaptersForFacade fill:#fff8e1,stroke:#ff8f00
    style NanobotCore fill:#fce4ec,stroke:#c2185b
```

---

## 5. 数据流设计

### 5.1 状态变更数据流

```mermaid
flowchart TB
    subgraph Initiation["发起"]
        U["用户操作"]
    end
    
    subgraph Validation["验证"]
        V["请求验证"]
        A["权限检查"]
    end
    
    subgraph Processing["处理"]
        C["ConfigDiff 计算"]
        X["配置验证"]
        B["配置备份"]
    end
    
    subgraph Persistence["持久化"]
        P["保存配置"]
    end
    
    subgraph Notification["通知"]
        N["事件发布"]
        WS["WebSocket 广播"]
        S["状态更新"]
    end
    
    U --> V
    V --> A
    A --> C
    C --> X
    X --> B
    B --> P
    P --> N
    N --> WS
    N --> S
    
    style Initiation fill:#e1f5ff
    style Validation fill:#e3f2fd
    style Processing fill:#fff3e0
    style Persistence fill:#fff8e1
    style Notification fill:#e8f5e9
```

### 5.2 状态同步数据流

```mermaid
flowchart LR
    subgraph Sources["状态源"]
        A["Agent 状态"]
        C["Channel 状态"]
        S["Session 状态"]
        G["Gateway 状态"]
        Cr["Cron 状态"]
    end
    
    subgraph Collection["状态收集"]
        SM["StateFacade"]
    end
    
    subgraph Caching["缓存层"]
        Cache["状态缓存"]
    end
    
    subgraph Distribution["分发"]
        WS["WebSocket"]
        API["REST API"]
        Alert["告警系统"]
    end
    
    A & C & S & G & Cr --> SM
    SM --> Cache
    Cache --> WS
    Cache --> API
    Cache --> Alert
```

### 5.3 统一状态获取流程

```mermaid
sequenceDiagram
    participant F as Frontend
    participant API
    participant SM as StateFacade
    participant AF as AgentFacade
    participant CF as ChannelFacade
    participant SF as SessionFacade
    participant GF as GatewayBridge
    participant CF2 as CronFacade
    
    F->>API: GET /api/v1/status
    API->>SM: get_unified_status()
    
    par 并行收集
        SM->>AF: health_check()
        SM->>CF: health_check()
        SM->>SF: get_summary()
        SM->>GF: get_status()
        SM->>CF2: health_check()
    end
    
    AF-->>SM: AgentStatus
    CF-->>SM: ChannelStatus
    SF-->>SM: SessionStatus
    GF-->>SM: GatewayStatus
    CF2-->>SM: CronStatus
    
    SM->>SM: aggregate()
    SM-->>API: UnifiedStatus
    API-->>F: status response
```

---

## 6. API 设计

### 6.1 API 分层

```mermaid
flowchart TB
    subgraph External["对外 API (保持兼容)"]
        E1["/api/v1/bots"]
        E2["/api/v1/sessions"]
        E3["/api/v1/channels"]
        E4["/api/v1/agents"]
        E5["/api/v1/cron"]
    end
    
    subgraph Internal["内部 API (新设计)"]
        I1["/api/v1/status"]
        I2["/api/v1/operations"]
    end
    
    subgraph Facade["Facade 层"]
        F1["StateFacade"]
        F2["AgentFacade"]
        F3["ChannelFacade"]
    end
    
    External --> F2
    External --> F3
    Internal --> F1
    F1 --> F2
    F1 --> F3
    
    style External fill:#e1f5ff,stroke:#01579b
    style Internal fill:#e8f5e9,stroke:#2e7d32
    style Facade fill:#fff3e0,stroke:#e65100
```

### 6.2 操作请求格式

```mermaid
flowchart TB
    A["OperationRequest"] --> B["operation: str"]
    A --> C["resource_type: str"]
    A --> D["resource_id: str"]
    A --> E["data: Dict"]
    
    B --> B1["CREATE"]
    B --> B2["UPDATE"]
    B --> B3["DELETE"]
    B --> B4["START"]
    B --> B5["STOP"]
    B --> B6["RESTART"]
    B --> B7["REFRESH"]
    B --> B8["TEST"]
    
    C --> C1["agent"]
    C --> C2["channel"]
    C --> C3["session"]
    C --> C4["cron"]
    C --> C5["provider"]
    C --> C6["skill"]
    C --> C7["mcp"]
    
    E --> E1["{name: xxx, ...}"]
```

### 6.3 响应格式

```mermaid
flowchart TB
    subgraph Success["成功响应"]
        S1["success: true"]
        S2["message: str"]
        S3["data: Dict"]
        S4["timestamp: str"]
    end
    
    subgraph Error["错误响应"]
        E1["success: false"]
        E2["message: str"]
        E3["error: str"]
        E4["timestamp: str"]
    end
```

---

## 7. 配置管理

### 7.1 配置管理架构

```mermaid
flowchart TB
    subgraph ConfigSources["配置来源"]
        CF["配置文件<br/>config.json"]
        ENV[".env 文件"]
        DEFAULT["nanobot 默认"]
    end
    
    subgraph ConfigLayer["配置层"]
        Loader["ConfigLoader"]
        Validator["ConfigValidator"]
        Diff["ConfigDiffCalculator"]
        Backup["ConfigBackup"]
    end
    
    subgraph ConfigConsumers["配置消费者"]
        Nanobot["nanobot Config"]
        Facade["Facade"]
        UI["前端配置页"]
    end
    
    CF & ENV & DEFAULT --> Loader
    Loader --> Validator
    Validator --> Diff
    Diff --> Backup
    Backup --> Nanobot
    Facade --> Loader
    Facade --> Diff
    UI --> Facade
    
    style ConfigLayer fill:#fff3e0
    style ConfigSources fill:#e1f5ff
    style ConfigConsumers fill:#e8f5e9
```

### 7.2 配置变更验证

```mermaid
flowchart TB
    A["接收配置变更"] --> B["Schema 验证"]
    B --> C{"通过?"}
    C -->|否| E["返回 Schema 错误"]
    C -->|是| F["业务规则验证"]
    F --> G{"通过?"}
    G -->|否| H["返回规则错误"]
    G -->|是| I["冲突检测"]
    I --> J{"有冲突?"}
    J -->|是| K["返回冲突警告"]
    J -->|否| L["允许变更"]
    
    E -.->|"返回"| A
    H -.->|"返回"| A
    K -.->|"返回"| A
```

---

## 8. 改造实施计划

### 8.1 阶段划分

```mermaid
gantt
    title 改造实施计划
    dateFormat  YYYY-MM-DD
    
    section Phase 1: 基础设施
    创建基础接口定义         :a1, 2026-03-30, 1 week
    创建配置管理层           :a2, 2026-04-06, 1 week
    
    section Phase 2: Gateway 适配
    创建 Gateway 适配器       :b1, 2026-04-13, 1 week
    实现 Gateway 状态观察     :b2, 2026-04-20, 1 week
    
    section Phase 3: 核心 Facade
    Agent/Channel Facade     :c1, 2026-04-27, 1 week
    Session/Cron Facade      :c2, 2026-05-04, 1 week
    
    section Phase 4: 状态整合
    StateFacade 实现         :d1, 2026-05-11, 1 week
    API 层适配               :d2, 2026-05-18, 1 week
    
    section Phase 5: 验证与优化
    兼容性验证               :e1, 2026-05-25, 1 week
    性能优化                 :e2, 2026-06-01, 1 week
```

### 8.2 各阶段交付物

#### Phase 1: 基础设施

| 交付物 | 文件 | 说明 |
|--------|------|------|
| 基础接口 | `facade/base.py` | BaseManager、OperationResult、HealthCheckResult |
| 配置加载 | `facade/config/loader.py` | 统一配置加载接口 |
| 配置验证 | `facade/config/validator.py` | 配置验证规则 |

#### Phase 2: Gateway 适配

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Gateway 适配器 | `gateway/adapter.py` | IGatewayAdapter 实现 |
| Gateway 桥接 | `extension/gateway_bridge.py` | GatewayBridge 实现 |
| 事件订阅 | `gateway/events.py` | Gateway 事件定义 |

#### Phase 3: 核心 Facade

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Agent 管理 | `facade/agent/manager.py` | AgentFacade |
| Channel 管理 | `facade/channel/manager.py` | ChannelFacade |
| Session 管理 | `facade/session/manager.py` | SessionFacade |
| Cron 管理 | `facade/cron/manager.py` | CronFacade |

#### Phase 4: 状态整合

| 交付物 | 文件 | 说明 |
|--------|------|------|
| 统一状态 | `facade/state/manager.py` | StateFacade |
| API 适配 | `api/facade/status.py` | 适配 Facade |
| WebSocket 适配 | `websocket/handler.py` | 适配 Facade |

#### Phase 5: 验证与优化

| 交付物 | 说明 |
|--------|------|
| 单元测试 | 各 Facade 单元测试 |
| 集成测试 | API 端点集成测试 |
| 性能测试 | 状态获取性能基准 |

---

## 附录

### A. 核心原则清单

| 原则 | 约束级别 | 违反后果 |
|------|----------|----------|
| nanobot 源码绝对不可修改 | 硬约束 | 架构退化 |
| 前端 API 完全兼容 | 硬约束 | 前端需改动 |
| Gateway 独立运行 | 硬约束 | Gateway 依赖后端 |
| Facade 仅通过配置交互 | 约束 | 直接调用 nanobot |
| 扩展层仅做适配不做修改 | 约束 | nanobot 代码污染 |

### B. 依赖关系白名单

```mermaid
flowchart TB
    subgraph Allowed["允许的依赖 (白名单)"]
        A1["facade --> extension"]
        A2["facade --> gateway_adapter"]
        A3["extension --> nanobot.config"]
        A4["extension --> nanobot.schema"]
        A5["gateway_adapter --> nanobot.gateway"]
        A6["api --> facade"]
        A7["websocket --> facade"]
    end
    
    subgraph Forbidden["禁止的依赖"]
        F1["facade -.x. nanobot.agent.loop"]
        F2["facade -.x. nanobot.channels"]
        F3["facade -.x. nanobot.session"]
        F4["extension -.x. nanobot 内部实现"]
    end
    
    style Allowed fill:#e8f5e9,stroke:#2e7d32
    style Forbidden fill:#ffebee,stroke:#c62828
```

### C. 文件变更清单

| 变更类型 | 文件 | 变更说明 |
|----------|------|----------|
| 新增 | `facade/` | 整个目录新增 |
| 新增 | `gateway/` | Gateway 适配器目录 |
| 重构 | `extension/__init__.py` | 适配 Facade |
| 适配 | `api/state.py` | 使用 Facade |
| 适配 | `websocket/handler.py` | 使用 Facade |
| 适配 | `main.py` | 初始化 Facade |
| 不变 | `nanobot/` | **绝对不可修改** |
| 不变 | `console/web/` | **绝对不可修改** |
