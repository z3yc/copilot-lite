# Copilot-Lite 架构文档

> 本文档描述 Copilot-Lite 的系统架构、核心流程与数据模型，图均使用 Mermaid 绘制。

---

## 1. 系统总体架构（Container 视图）

```mermaid
graph TB
    subgraph Users["用户"]
        U1[日常使用<br/>CLI]
        U2[Web 浏览器<br/>知识库管理]
    end

    subgraph Client["客户端层"]
        CLI["CLI 客户端<br/>typer + rich"]
        WEB["Web UI<br/>React + Vite + TS"]
    end

    subgraph Backend["后端服务（Docker 容器）"]
        API["FastAPI 应用<br/>REST + SSE + WebSocket"]
        subgraph Core["Agent 核心"]
            ORCH["对话编排器<br/>会话状态机"]
            MEM["记忆服务<br/>短期摘要 + 长期向量"]
            TOOL["工具调度器<br/>注册表 + Function Calling"]
            RAG["RAG 编排器<br/>检索→重排→生成"]
        end
        subgraph Tools["工具层"]
            T_TODO["Todo 工具"]
            T_KB["知识库检索工具"]
            T_CODE["代码检索/沙箱工具"]
            T_SYS["监控/通知工具"]
        end
    end

    subgraph Infra["基础设施（Docker Compose）"]
        PG[("PostgreSQL<br/>业务数据")]
        QD[("Qdrant<br/>向量库")]
        RD[("Redis<br/>缓存/会话/队列")]
        FS[("数据卷<br/>文档原件")]
        NX["Nginx<br/>静态资源 + 反向代理"]
    end

    LLM["DeepSeek API<br/>（外部）"]

    U1 -->|HTTP/SSE| CLI
    U2 -->|HTTPS| NX
    NX --> API
    CLI -->|HTTP/SSE| API
    API --> ORCH
    ORCH --> MEM
    ORCH --> TOOL
    ORCH --> RAG
    TOOL --> T_TODO
    TOOL --> T_KB
    TOOL --> T_CODE
    TOOL --> T_SYS
    T_KB --> RAG
    RAG --> QD
    ORCH -->|对话补全 + Function Calling| LLM
    MEM --> QD
    MEM --> RD
    ORCH --> PG
    TOOL --> PG
    TOOL --> FS
    T_CODE --> FS
    PIPE["文档解析 Pipeline<br/>（后台任务）"] --> QD
    PIPE --> FS
    FS --> PIPE
```

---

## 2. Agent 对话时序（ReAct + Function Calling）

```mermaid
sequenceDiagram
    autonumber
    participant U as 用户
    participant O as 对话编排器
    participant M as 记忆服务
    participant L as DeepSeek API
    participant R as 工具注册表
    participant T as 具体工具

    U->>O: 发送消息
    O->>M: 加载记忆（短期上下文 + 长期事实召回）
    M-->>O: 注入记忆的上下文包
    loop ReAct 循环（最多 N 轮）
        O->>L: 消息 + 系统提示 + 工具定义
        L-->>O: 回复（文本 或 tool_calls）
        alt 包含 tool_calls
            O->>R: 解析并查找工具
            R-->>O: 工具函数
            O->>T: 执行调用（带参数校验）
            T-->>O: 结构化结果
            O->>L: 追加工具结果，再次请求
        else 纯文本回复
            O-->>U: 流式输出回答
            Note over O: 对话结束
        end
    end
    O->>M: 异步更新记忆（摘要 + 提取新事实）
```

---

## 3. RAG 知识库流程（Ingest → Retrieve → Generate）

```mermaid
flowchart LR
    subgraph Ingest["① 文档摄取（后台 Pipeline）"]
        A1[多格式输入<br/>MD/PDF/DOCX/代码/网页]
        A2[解析与清洗<br/>去水印/去噪/结构提取]
        A3[智能分块<br/>标题层级/代码结构/语义边界]
        A4[块级元数据<br/>来源/页码/路径/时间]
        A5[向量化嵌入<br/>DeepSeek/本地嵌入模型]
        A6[(Qdrant<br/>向量 + 全文索引)]
        A1 --> A2 --> A3 --> A4 --> A5 --> A6
    end

    subgraph Retrieve["② 检索"]
        B1[用户问题]
        B2[Query 改写/扩展]
        B3[向量检索 TopK]
        B4[BM25 关键词检索 TopK]
        B5[融合排序<br/>RRF 加权融合]
        B6[Rerank 重排<br/>相关性精排]
        B1 --> B2 --> B3
        B2 --> B4
        B3 --> B5
        B4 --> B5 --> B6
    end

    subgraph Generate["③ 生成"]
        C1[上下文组装<br/>TopK 块 + 引用元数据]
        C2[LLM 生成<br/>带引用标注的回答]
        C3[引用溯源展示<br/>来源文件/页码/片段]
        C1 --> C2 --> C3
    end

    A6 --> B3
    B6 --> C1
```

---

## 4. 双层记忆系统

```mermaid
flowchart TB
    subgraph Short["短期记忆（会话级）"]
        S1[原始消息窗口<br/>最近 K 条]
        S2[滚动摘要<br/>窗口溢出时 LLM 压缩]
        S3[(Redis<br/>会话级缓存)]
        S1 --> S2 --> S3
    end

    subgraph Long["长期记忆（跨会话）"]
        L1[事实提取<br/>对话结束后异步抽取]
        L2[事实向量化]
        L3[(Qdrant<br/>memory 集合)]
        L4[相关性召回<br/>新对话开始时注入]
        L1 --> L2 --> L3 --> L4
    end

    subgraph Rules["写入/读取规则"]
        R1[写入时机：会话结束/事件触发]
        R2[读取时机：会话开始 + 每轮前置]
        R3[去重与时效：同事实覆盖、过期淘汰]
    end

    Short --> Rules
    Long --> Rules
```

---

## 5. 数据模型（ER 图）

```mermaid
erDiagram
    USER ||--o{ SESSION : "拥有"
    USER ||--o{ TODO : "拥有"
    SESSION ||--o{ MESSAGE : "包含"
    USER ||--o{ DOCUMENT : "拥有"
    DOCUMENT ||--o{ CHUNK : "切分为"
    CHUNK ||--o{ EMBEDDING : "向量化为"
    DOCUMENT ||--o{ INGEST_JOB : "处理于"
    USER ||--o{ MEMORY_FACT : "沉淀为"

    USER {
        uuid id PK
        string username UK
        string password_hash
        string role
        timestamp created_at
    }
    SESSION {
        uuid id PK
        uuid user_id FK
        string title
        string summary
        timestamp created_at
        timestamp updated_at
    }
    MESSAGE {
        uuid id PK
        uuid session_id FK
        string role
        text content
        jsonb metadata
        timestamp created_at
    }
    TODO {
        uuid id PK
        uuid user_id FK
        string title
        string status
        int priority
        date due_date
        timestamp created_at
    }
    DOCUMENT {
        uuid id PK
        uuid user_id FK
        string title
        string source_type
        string storage_path
        string status
        jsonb metadata
        timestamp created_at
    }
    CHUNK {
        uuid id PK
        uuid document_id FK
        int chunk_index
        text content
        jsonb metadata
    }
    EMBEDDING {
        uuid id PK
        uuid chunk_id FK
        vector embedding
        string model
    }
    INGEST_JOB {
        uuid id PK
        uuid document_id FK
        string status
        text error
        timestamp started_at
        timestamp finished_at
    }
    MEMORY_FACT {
        uuid id PK
        uuid user_id FK
        text fact
        string category
        float confidence
        timestamp created_at
        timestamp expires_at
    }
```

---

## 6. 部署拓扑（本地 / 云端模式）

```mermaid
graph LR
    subgraph Local["本地模式 RUN_MODE=local"]
        LAPI["FastAPI (host 进程)"]
        LPG[("PostgreSQL (Docker)")]
        LQD[("Qdrant (Docker)")]
        LRD[("Redis (Docker)")]
        LAPI --- LPG
        LAPI --- LQD
        LAPI --- LRD
    end

    subgraph Cloud["云端模式 RUN_MODE=cloud（2C4G 轻量服务器）"]
        CNX["Nginx (80/443)"]
        CAP["FastAPI (容器)"]
        CPG[("PostgreSQL (容器)")]
        CQD[("Qdrant (容器)")]
        CRD[("Redis (容器)")]
        CFS[("数据卷")]
        CNX --> CAP
        CAP --- CPG
        CAP --- CQD
        CAP --- CRD
        CAP --- CFS
    end

    LLM["DeepSeek API"] -.-> LAPI
    LLM -.-> CAP
```
