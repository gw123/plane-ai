# Plane CE 架构文档

> 本文档描述 Plane CE 的系统架构、技术栈、业务数据模型及核心流程。

---

## 目录

- [一、技术栈总览](#一技术栈总览)
- [二、系统架构](#二系统架构)
  - [2.1 服务依赖关系](#21-服务依赖关系)
  - [2.2 生产环境网络拓扑](#22-生产环境网络拓扑)
  - [2.3 本地开发 vs 生产环境端口对照](#23-本地开发-vs-生产环境端口对照)
- [三、业务数据模型](#三业务数据模型)
  - [3.1 整体层级关系](#31-整体层级关系)
  - [3.2 实体关系图（ER）](#32-实体关系图er)
  - [3.3 业务流程关系图](#33-业务流程关系图)
  - [3.4 Issue 与 Cycle / Module 归属规则](#34-issue-与-cycle--module-归属规则)
  - [3.5 Workspace（工作区）](#35-workspace工作区)
  - [3.6 Project（项目）](#36-project项目)
  - [3.7 Issue（工作项）](#37-issue工作项)
  - [3.8 Cycle（周期）](#38-cycle周期)
  - [3.9 Module（模块）](#39-module模块)
  - [3.10 Page（页面）](#310-page页面)
  - [3.11 推荐工作流](#311-推荐工作流)
- [四、核心业务流程](#四核心业务流程)
  - [4.1 用户登录流程](#41-用户登录流程)
  - [4.2 创建工作项流程](#42-创建工作项流程)
  - [4.3 文件上传流程](#43-文件上传流程)
  - [4.4 异步任务流程](#44-异步任务流程)
  - [4.5 实例初始化流程](#45-实例初始化流程)

---

## 一、技术栈总览

| 组件               | 技术                    | 职责                                      |
| :----------------- | :---------------------- | :---------------------------------------- |
| **web**            | Next.js + React         | 主应用界面（工作项、看板、周期等）        |
| **admin**          | Vite + React            | 实例管理后台（God Mode）                  |
| **space**          | Next.js + React         | 公开项目空间（免登录访问）                |
| **live**           | Node.js + WebSocket     | 实时协作服务（Page 多人编辑）             |
| **api**            | Django + DRF + Gunicorn | REST API，核心业务逻辑                    |
| **worker**         | Celery                  | 异步任务（邮件、导出、AI 等）             |
| **beat-worker**    | Celery Beat             | 定时任务调度                              |
| **migrator**       | Django manage.py        | 数据库结构迁移（启动时一次性运行）        |
| **proxy**          | Caddy / Nginx           | 反向代理，统一入口（仅生产）              |
| **PostgreSQL**     | postgres:15.7           | 主数据库                                  |
| **Redis / Valkey** | valkey:7.2              | 缓存 + Session + 分布式锁                 |
| **RabbitMQ**       | rabbitmq:3.13           | Celery 消息队列                           |
| **MinIO**          | minio/minio             | S3 兼容对象存储（附件 / 图片 / 导出文件） |

---

## 二、系统架构

### 2.1 服务依赖关系

```mermaid
graph TD
    Browser(["🌐 浏览器"])

    subgraph Frontend["  前端服务  "]
        web(["web\nNext.js 主应用"])
        admin(["admin\nGod Mode 管理后台"])
        space(["space\n公开空间"])
        live(["live\nNode.js 实时协作"])
    end

    subgraph Backend["  后端服务  "]
        api(["API\nDjango + Gunicorn"])
        worker(["worker\nCelery 异步任务"])
        beat(["beat-worker\nCelery 定时任务"])
        migrator(["migrator\nDB 迁移（一次性）"])
    end

    subgraph Storage["  存储层  "]
        pg(["🐘 PostgreSQL\n主数据库"])
        redis(["⚡ Redis / Valkey\n缓存 + 锁"])
        mq(["📨 RabbitMQ\n消息队列"])
        minio(["🪣 MinIO\n对象存储"])
    end

    Browser --> web & admin & space & live
    web & admin & space & live -->|REST API| api
    live <-->|WebSocket| Browser

    api --> pg & redis & minio
    api -->|推送任务| mq

    worker -->|消费| mq
    worker --> pg & minio

    beat -->|定时触发| mq
    beat --> redis

    migrator --> pg
    migrator -.->|完成后退出| api

    style Browser fill:#e8f4fd,stroke:none,color:#2c3e50,rx:20
    style api     fill:#3498db,stroke:none,color:#fff,rx:8
    style worker  fill:#9b59b6,stroke:none,color:#fff,rx:8
    style beat    fill:#8e44ad,stroke:none,color:#fff,rx:8
    style migrator fill:#95a5a6,stroke:none,color:#fff,rx:8
    style web     fill:#2ecc71,stroke:none,color:#fff,rx:8
    style admin   fill:#27ae60,stroke:none,color:#fff,rx:8
    style space   fill:#1abc9c,stroke:none,color:#fff,rx:8
    style live    fill:#16a085,stroke:none,color:#fff,rx:8
    style pg      fill:#f39c12,stroke:none,color:#fff,rx:8
    style redis   fill:#e74c3c,stroke:none,color:#fff,rx:8
    style mq      fill:#e67e22,stroke:none,color:#fff,rx:8
    style minio   fill:#d35400,stroke:none,color:#fff,rx:8
```

---

### 2.2 生产环境网络拓扑

```mermaid
graph LR
    Internet(["🌍 外网请求"])

    subgraph proxy["  反向代理（Caddy / Nginx）  "]
        router(["路由规则\n:80 / :443"])
    end

    subgraph app["  应用服务（Docker 内网）  "]
        web(["web :3000"])
        admin(["admin :3000"])
        space(["space :3000"])
        live(["live :3000"])
        api(["api :8000"])
        minio(["minio :9000"])
    end

    Internet --> router

    router -->|"/*"| web
    router -->|"/god-mode/*"| admin
    router -->|"/spaces/*"| space
    router -->|"/live/*"| live
    router -->|"/api/*  /auth/*"| api
    router -->|"/uploads/*"| minio

    style Internet fill:#e8f4fd,stroke:none,color:#2c3e50,rx:20
    style router  fill:#34495e,stroke:none,color:#fff,rx:8
    style web     fill:#2ecc71,stroke:none,color:#fff,rx:8
    style admin   fill:#27ae60,stroke:none,color:#fff,rx:8
    style space   fill:#1abc9c,stroke:none,color:#fff,rx:8
    style live    fill:#16a085,stroke:none,color:#fff,rx:8
    style api     fill:#3498db,stroke:none,color:#fff,rx:8
    style minio   fill:#d35400,stroke:none,color:#fff,rx:8
```

---

### 2.3 本地开发 vs 生产环境端口对照

| 服务              | 本地开发端口 | 生产环境访问方式            |
| :---------------- | :----------: | :-------------------------- |
| web（主应用）     |   `:3000`    | 反向代理 `/*`               |
| admin（God Mode） |   `:3001`    | 反向代理 `/god-mode/*`      |
| space（公开空间） |   `:3002`    | 反向代理 `/spaces/*`        |
| live（实时协作）  |   `:3100`    | 反向代理 `/live/*`          |
| API               |   `:8080`    | 反向代理 `/api/*` `/auth/*` |
| MinIO S3          |   `:9000`    | 反向代理 `/uploads/*`       |
| MinIO 控制台      |   `:9090`    | 不对外暴露                  |
| PostgreSQL        |   `:5432`    | 不对外暴露                  |
| Redis             |   `:6379`    | 不对外暴露                  |

---

## 三、业务数据模型

### 3.1 整体层级关系

```
Instance（实例）
└── Workspace（工作区）
    ├── WorkspaceMember（成员）
    ├── Team（团队）
    └── Project（项目）× 多个
        ├── ProjectMember（项目成员）
        ├── State（工作项状态定义）
        ├── Label（标签）
        ├── Estimate（工时估算方案）
        ├── Issue（工作项）× 多个
        │   ├── Sub-Issue（子任务，自引用）
        │   ├── IssueComment（评论）
        │   ├── IssueActivity（操作日志）
        │   └── IssueAttachment（附件）
        ├── Cycle（周期 / Sprint）× 多个
        │   └── CycleIssue（周期与工作项关联表）
        ├── Module（功能模块）× 多个
        │   └── ModuleIssue（模块与工作项关联表）
        └── Page（协作文档，Workspace 级，可关联多个 Project）
            └── PageVersion（历史版本）
```

---

### 3.2 实体关系图（ER）

```mermaid
erDiagram
    Instance ||--o{ Workspace : "包含"
    Workspace ||--o{ Project : "包含"
    Workspace ||--o{ WorkspaceMember : "拥有"
    Workspace ||--o{ Team : "拥有"
    Workspace ||--o{ Page : "拥有"

    Project ||--o{ Issue : "包含"
    Project ||--o{ Cycle : "包含"
    Project ||--o{ Module : "包含"
    Project ||--o{ ProjectMember : "拥有"
    Project ||--o{ State : "定义状态"
    Project ||--o{ Label : "定义标签"
    Project }o--o{ Page : "关联（ProjectPage）"

    Issue ||--o{ Issue : "子任务（自引用）"
    Issue ||--o{ IssueComment : "评论"
    Issue ||--o{ IssueActivity : "操作日志"
    Issue ||--o{ IssueAttachment : "附件"
    Issue }o--|| State : "当前状态"

    Cycle ||--o{ CycleIssue : "包含"
    Module ||--o{ ModuleIssue : "包含"
    CycleIssue }o--|| Issue : "引用"
    ModuleIssue }o--|| Issue : "引用"

    Page ||--o{ PageVersion : "历史版本"

    User ||--o{ WorkspaceMember : "加入"
    User ||--o{ ProjectMember : "加入"
    User ||--o{ Issue : "创建 / 负责"
```

---

### 3.3 业务流程关系图

```mermaid
flowchart TD
    WS(["🏢 Workspace\n工作区"])
    PROJ(["🗂️ Project\n项目"])
    PAGE(["📄 Page\n需求文档 / Wiki"])
    ISSUE(["🎯 Issue\n工作项"])
    SUB(["🎯 Sub-Issue\n子任务"])
    MOD(["📦 Module\n功能模块"])
    CYC(["🔄 Cycle\n迭代周期 Sprint"])

    WS -->|"包含多个"| PROJ
    PROJ -->|"包含"| ISSUE
    PROJ -->|"包含"| CYC
    PROJ -->|"包含"| MOD
    PROJ -->|"关联"| PAGE

    PAGE -->|"需求拆解"| ISSUE
    ISSUE -->|"拆分子任务"| SUB

    ISSUE -->|"归入（可多个）"| MOD
    ISSUE -->|"纳入（同时只能一个）"| CYC

    MOD -->|"按功能维度追踪进度"| ISSUE
    CYC -->|"按时间维度追踪进度"| ISSUE

    style WS   fill:#4A90D9,stroke:none,color:#fff,rx:20
    style PROJ fill:#5BA85A,stroke:none,color:#fff,rx:20
    style PAGE fill:#1ABC9C,stroke:none,color:#fff,rx:20
    style ISSUE fill:#E8A838,stroke:none,color:#fff,rx:20
    style SUB  fill:#E8A838,stroke:none,color:#fff,rx:20,opacity:0.7
    style MOD  fill:#9B59B6,stroke:none,color:#fff,rx:20
    style CYC  fill:#E74C3C,stroke:none,color:#fff,rx:20
```

---

### 3.4 Issue 与 Cycle / Module 归属规则

```mermaid
flowchart LR
    I1(["🎯 Issue A"])
    I2(["🎯 Issue B"])
    I3(["🎯 Issue C"])
    I4(["🎯 Issue D"])

    subgraph MOD["  📦 Module（功能维度，可多属）  "]
        M1(["用户认证模块"])
        M2(["支付模块"])
    end

    subgraph CYC["  🔄 Cycle（时间维度，同时只能一个）  "]
        C1(["第 3 周期\n4.21 - 5.04"])
        C2(["第 4 周期\n5.05 - 5.18"])
    end

    I1 --> M1
    I2 --> M1
    I3 --> M2
    I4 --> M2

    I1 --> C1
    I2 --> C2
    I3 --> C1
    I4 --> C2

    style I1 fill:#E8A838,stroke:none,color:#fff,rx:20
    style I2 fill:#E8A838,stroke:none,color:#fff,rx:20
    style I3 fill:#E8A838,stroke:none,color:#fff,rx:20
    style I4 fill:#E8A838,stroke:none,color:#fff,rx:20
    style M1 fill:#9B59B6,stroke:none,color:#fff,rx:20
    style M2 fill:#9B59B6,stroke:none,color:#fff,rx:20
    style C1 fill:#E74C3C,stroke:none,color:#fff,rx:20
    style C2 fill:#E74C3C,stroke:none,color:#fff,rx:20
```

> **规则说明：**
>
> - ✅ 一个 Issue 可同时归属**多个 Module**（跨功能模块）
> - ⚠️ 一个 Issue **同时只能在一个 Cycle** 中（不允许跨期重叠）
> - 🔁 Issue 从 Cycle / Module 移除后，仍存在于 Project 中

---

### 3.5 Workspace（工作区）

> 整个系统的顶层容器，对应一个公司或团队组织。

**核心属性：**

| 属性                | 类型           | 说明                                   |
| :------------------ | :------------- | :------------------------------------- |
| `name`              | 字符串         | 工作区名称（最长 80 字符）             |
| `slug`              | slug           | URL 标识符，全局唯一（如 `/lixiang/`） |
| `owner`             | FK → User      | 创建者，拥有最高权限                   |
| `logo_asset`        | FK → FileAsset | Logo 图片（存储于 MinIO）              |
| `organization_size` | 字符串         | 组织规模                               |
| `timezone`          | 字符串         | 时区，新建 Project 默认继承此值        |
| `background_color`  | 字符串         | 背景颜色（随机生成）                   |

**成员角色（WorkspaceMember）：**

| 角色   | 权重值 | 权限说明                     |
| :----- | :----: | :--------------------------- |
| Admin  |   20   | 可管理工作区设置、成员、计费 |
| Member |   15   | 可创建和管理项目、工作项     |
| Guest  |   5    | 只读，受项目级开关控制       |

**关联关系：**

- 一个 Workspace 包含多个 **Project**
- **Page** 属于 Workspace 级，可跨项目关联
- **Team** 在 Workspace 级别管理，可跨项目协作

---

### 3.6 Project（项目）

> 工作的核心组织单元，对应一个产品线、服务或业务模块。

**核心属性：**

| 属性               | 说明                                                                     |
| :----------------- | :----------------------------------------------------------------------- |
| `name`             | 项目名称（Workspace 内唯一）                                             |
| `identifier`       | 缩写前缀，最长 12 字符，自动大写（如 `PROJ`），用于 Issue 编号 `PROJ-42` |
| `network`          | `0 = Secret`（私有）/ `2 = Public`（公开）                               |
| `project_lead`     | 项目负责人                                                               |
| `default_assignee` | 新建 Issue 的默认指派人                                                  |
| `default_state`    | 新建 Issue 的默认状态                                                    |
| `estimate`         | 关联的工时估算方案                                                       |
| `timezone`         | 项目时区（新建时继承 Workspace，可覆盖）                                 |
| `archive_in`       | 多少个月后自动归档 Issue（`0` = 不自动，最大 12）                        |
| `close_in`         | 多少个月后自动关闭 Issue（`0` = 不自动，最大 12）                        |

**功能开关（可按项目独立启用）：**

| 开关字段                   | 默认值 | 说明                     |
| :------------------------- | :----: | :----------------------- |
| `cycle_view`               | ❌ 关  | 是否启用周期（Sprint）   |
| `module_view`              | ❌ 关  | 是否启用模块             |
| `page_view`                | ✅ 开  | 是否启用页面文档         |
| `issue_views_view`         | ❌ 关  | 是否启用自定义视图       |
| `intake_view`              | ❌ 关  | 是否启用需求池（Intake） |
| `is_time_tracking_enabled` | ❌ 关  | 是否启用时间追踪         |
| `is_issue_type_enabled`    | ❌ 关  | 是否启用 Issue 类型区分  |
| `guest_view_all_features`  | ❌ 关  | Guest 是否可见所有功能   |

---

### 3.7 Issue（工作项）

> 系统最核心的工作单元，一条 Issue 代表一项具体的工作任务。

**核心属性：**

| 属性                              | 说明                                                  |
| :-------------------------------- | :---------------------------------------------------- |
| `name`                            | 标题                                                  |
| `description_html`                | 富文本描述                                            |
| `state`                           | 当前状态（关联项目自定义的 State 对象）               |
| `priority`                        | 优先级：`urgent` / `high` / `medium` / `low` / `none` |
| `assignees`                       | 负责人（支持多人，M2M）                               |
| `label`                           | 标签（支持多个，M2M）                                 |
| `start_date` / `due_date`         | 开始日期 / 截止日期                                   |
| `estimate_point`                  | 工时估算点数                                          |
| `sequence_id`                     | 项目内自增编号，与 `identifier` 拼成 `PROJ-42`        |
| `parent`                          | 父 Issue（自引用，支持多层子任务）                    |
| `external_source` / `external_id` | 外部系统导入来源（如 Jira、GitHub）                   |

**State 状态分组：**

```
backlog → unstarted → started → completed → cancelled
```

State 由项目自定义，分为以上五种内置分组，每组可创建多个自定义状态。

---

### 3.8 Cycle（周期）

> 固定时间盒，类似 Scrum Sprint，用于时间驱动的迭代管理。

**核心属性：**

| 属性                      | 说明                                                 |
| :------------------------ | :--------------------------------------------------- |
| `name`                    | 周期名称                                             |
| `start_date` / `end_date` | 严格的起止日期，决定周期状态                         |
| `owned_by`                | 周期负责人                                           |
| `timezone`                | 时区（跨区域团队保持日期一致）                       |
| `progress_snapshot`       | 定期进度快照，用于燃尽图                             |
| `status`                  | 由日期自动判断：`upcoming` / `current` / `completed` |

**典型使用节奏：**

```
创建 Cycle（每两周）
    │
    ├── 从各 Module 中挑选本期 Issue 放入
    │
    ├── 团队聚焦执行
    │
    └── 结束后 Review，未完成 Issue 转入下一个 Cycle
```

---

### 3.9 Module（模块）

> 按功能 / 特性组织工作的容器，时间线灵活，适合内容驱动的交付管理。

**核心属性：**

| 属性                         | 说明                                                                                   |
| :--------------------------- | :------------------------------------------------------------------------------------- |
| `name`                       | 模块名称                                                                               |
| `description`                | 富文本描述                                                                             |
| `start_date` / `target_date` | 计划时间线（灵活，不强制节奏）                                                         |
| `status`                     | 手动设置：`backlog` / `planned` / `in-progress` / `paused` / `completed` / `cancelled` |
| `lead`                       | 模块负责人                                                                             |
| `members`                    | 参与成员（M2M）                                                                        |

**Cycle vs Module 核心区别：**

| 维度       | 🔄 Cycle（周期）     | 📦 Module（模块）    |
| :--------- | :------------------- | :------------------- |
| 时间管理   | 固定时间盒，节奏驱动 | 灵活时间线，交付驱动 |
| 状态判断   | 由日期自动计算       | 手动维护状态         |
| 典型用途   | Sprint 冲刺迭代      | 功能模块交付         |
| Issue 归属 | 同时只能属于一个     | 可同时属于多个       |

---

### 3.10 Page（页面）

> 协作文档，用于记录需求、设计方案、会议纪要、技术规范等知识内容。

**核心属性：**

| 属性            | 说明                                                    |
| :-------------- | :------------------------------------------------------ |
| `name`          | 文档标题                                                |
| `description_*` | 富文本内容（JSON / HTML / 纯文本多格式存储）            |
| `owned_by`      | 创建者 / 所有者                                         |
| `access`        | `0 = Public`（工作区可见）/ `1 = Private`（仅自己可见） |
| `parent`        | 父页面（支持多层嵌套，构建知识树）                      |
| `is_locked`     | 锁定后只有所有者可编辑                                  |
| `is_global`     | 是否为全局页面（跨项目可见）                            |

**特殊说明：**

- 属于 **Workspace 级**，不绑定单个 Project，通过 `ProjectPage` 关联表可挂载到多个项目
- 由 **live 服务**（Node.js WebSocket）支持多人实时协作编辑
- 有完整的 **PageVersion** 版本历史，支持回滚
- `PageLog` 记录页面内对 Issue、Cycle、Module 的引用关系

---

### 3.11 推荐工作流

```mermaid
flowchart LR
    A(["📄 1. 写需求文档\nPage"])
    B(["🎯 2. 创建工作项\nIssue"])
    C(["📦 3. 组织模块\nModule"])
    D(["🔄 4. 放入迭代\nCycle"])
    E(["✅ 5. 交付 & 回顾"])

    A -->|"拆解任务"| B
    B -->|"按功能归组"| C
    C -->|"挑选本期任务"| D
    D -->|"执行完成"| E
    E -->|"写复盘文档"| A

    style A fill:#1ABC9C,stroke:none,color:#fff,rx:20
    style B fill:#E8A838,stroke:none,color:#fff,rx:20
    style C fill:#9B59B6,stroke:none,color:#fff,rx:20
    style D fill:#E74C3C,stroke:none,color:#fff,rx:20
    style E fill:#5BA85A,stroke:none,color:#fff,rx:20
```

| 阶段 | 使用实体     | 核心操作                                      |
| :--: | :----------- | :-------------------------------------------- |
|  1   | Page         | 写清楚背景、目标、设计方案                    |
|  2   | Issue        | 从 Page 拆出可执行的最小任务（1~3天）         |
|  3   | Module       | 按功能边界将 Issue 归组（如「用户认证模块」） |
|  4   | Cycle        | 每两周从各 Module 挑 Issue 放入，聚焦执行     |
|  5   | Page + Cycle | 写复盘文档，未完成 Issue 转入下一个 Cycle     |

---

## 四、核心业务流程

### 4.1 用户登录流程

```mermaid
sequenceDiagram
    actor User as 用户
    participant Web as web
    participant API as API
    participant DB as PostgreSQL
    participant Cache as Redis

    User->>Web: 访问 /sign-in
    Web->>API: POST /auth/email-check/
    API->>DB: 查询邮箱是否存在
    DB-->>API: 返回结果
    API-->>Web: 返回账号状态

    alt 账号存在
        Web->>User: 显示密码输入框
        User->>Web: 填写密码
        Web->>API: POST /auth/sign-in/
        API->>DB: 验证密码
        DB-->>API: 验证通过
        API->>Cache: 写入 Session Token
        API-->>Web: 返回 Token + 用户信息
        Web->>User: 跳转 /workspace
    else 账号不存在
        Web->>User: 显示注册流程
    end
```

---

### 4.2 创建工作项流程

```mermaid
sequenceDiagram
    actor User as 用户
    participant Web as web
    participant API as API
    participant DB as PostgreSQL
    participant MQ as RabbitMQ
    participant Worker as Celery Worker
    participant Live as live（WebSocket）
    participant Others as 其他在线用户

    User->>Web: 点击「新建工作项」
    Web->>User: 弹出创建表单
    User->>Web: 填写信息并提交
    Web->>API: POST /api/v1/workspaces/{slug}/projects/{id}/issues/
    API->>DB: 写入 Issue 数据
    DB-->>API: 写入成功
    API-->>Web: 返回新建的 Issue
    Web->>User: 界面更新

    par 实时通知
        API->>Live: 广播变更事件
        Live->>Others: WebSocket 推送
        Others->>Others: 界面实时刷新
    and 异步任务
        API->>MQ: 推送「新 Issue」事件
        MQ->>Worker: 消费消息
        Worker->>Worker: 发送邮件通知 / 写入 Activity 日志
    end
```

---

### 4.3 文件上传流程

```mermaid
sequenceDiagram
    actor User as 用户
    participant Web as web
    participant API as API
    participant MinIO as MinIO

    User->>Web: 选择上传文件
    Web->>API: POST /api/v1/.../asset/
    API->>MinIO: 生成预签名上传 URL
    MinIO-->>API: 返回签名 URL
    API-->>Web: 返回签名 URL + asset_id

    Web->>MinIO: 直传文件（PUT 签名 URL）
    MinIO-->>Web: 上传成功

    Web->>API: PATCH /api/v1/.../asset/{id}/（标记完成）
    API->>MinIO: 验证文件存在
    API-->>Web: 返回最终访问 URL
    Web->>User: 显示文件预览
```

> **设计说明：** 浏览器直传 MinIO，API 仅负责签发 URL 和记录元数据，不承担文件传输带宽。

---

### 4.4 异步任务流程

```mermaid
flowchart LR
    API(["API\nDjango"])
    Beat(["Celery Beat\n定时调度"])
    MQ(["📨 RabbitMQ\n消息队列"])
    Worker(["⚙️ Celery Worker"])

    subgraph tasks["  任务类型  "]
        t1(["📧 邮件通知"])
        t2(["🔔 Webhook 推送"])
        t3(["📊 数据导出"])
        t4(["🤖 AI 功能调用"])
        t5(["📝 Activity 日志"])
        t6(["⏰ 自动归档 / 关闭"])
        t7(["🗑️ 清理过期数据"])
    end

    API -->|"用户操作触发"| MQ
    Beat -->|"定时触发"| MQ
    MQ -->|"消费"| Worker
    Worker --> t1 & t2 & t3 & t4 & t5
    Beat --> t6 & t7

    style API    fill:#3498db,stroke:none,color:#fff,rx:20
    style Beat   fill:#8e44ad,stroke:none,color:#fff,rx:20
    style MQ     fill:#e67e22,stroke:none,color:#fff,rx:20
    style Worker fill:#2ecc71,stroke:none,color:#fff,rx:20
    style t1 fill:#ecf0f1,stroke:none,color:#2c3e50,rx:20
    style t2 fill:#ecf0f1,stroke:none,color:#2c3e50,rx:20
    style t3 fill:#ecf0f1,stroke:none,color:#2c3e50,rx:20
    style t4 fill:#ecf0f1,stroke:none,color:#2c3e50,rx:20
    style t5 fill:#ecf0f1,stroke:none,color:#2c3e50,rx:20
    style t6 fill:#fadbd8,stroke:none,color:#2c3e50,rx:20
    style t7 fill:#fadbd8,stroke:none,color:#2c3e50,rx:20
```

**定时任务执行周期：**

| 任务               | 周期           |
| :----------------- | :------------- |
| 批量发送邮件通知   | 每 5 分钟      |
| 实例状态上报       | 每 6 小时      |
| 自动归档超期 Issue | 每天 01:00 UTC |
| 清理孤立文件资产   | 每天 02:00 UTC |
| 清理过期导出链接   | 每天 01:30 UTC |
| 硬删除软删除数据   | 每天 00:00 UTC |

---

### 4.5 实例初始化流程

```mermaid
flowchart TD
    Start(["🚀 Docker Compose Up"])

    subgraph infra["  基础设施启动（并行）  "]
        pg(["🐘 PostgreSQL"])
        redis(["⚡ Redis"])
        mq(["📨 RabbitMQ"])
        minio(["🪣 MinIO\n创建默认 Bucket"])
    end

    migrator(["migrator\nwait_for_db → migrate → 退出"])

    subgraph api_init["  API 初始化序列  "]
        w1(["wait_for_migrations"])
        w2(["register_instance\n生成唯一实例 ID"])
        w3(["configure_instance\n写入默认配置"])
        w4(["create_bucket\nMinIO 默认桶"])
        w5(["clear_cache\n清理 Redis"])
        w6(["🟢 Gunicorn 启动\n开始接受请求"])
    end

    subgraph workers["  后台服务（并行启动）  "]
        worker(["⚙️ Celery Worker"])
        beat(["🕐 Beat Worker"])
    end

    godmode(["管理员访问 /god-mode/\n完成实例配置"])
    ready(["✅ 系统就绪"])

    Start --> infra
    infra --> migrator
    migrator --> w1 --> w2 --> w3 --> w4 --> w5 --> w6
    infra --> workers
    w6 --> godmode --> ready
    workers --> ready

    style Start    fill:#3498db,stroke:none,color:#fff,rx:20
    style migrator fill:#95a5a6,stroke:none,color:#fff,rx:20
    style w1  fill:#dfe6e9,stroke:none,color:#2c3e50,rx:20
    style w2  fill:#dfe6e9,stroke:none,color:#2c3e50,rx:20
    style w3  fill:#dfe6e9,stroke:none,color:#2c3e50,rx:20
    style w4  fill:#dfe6e9,stroke:none,color:#2c3e50,rx:20
    style w5  fill:#dfe6e9,stroke:none,color:#2c3e50,rx:20
    style w6  fill:#2ecc71,stroke:none,color:#fff,rx:20
    style pg    fill:#f39c12,stroke:none,color:#fff,rx:20
    style redis fill:#e74c3c,stroke:none,color:#fff,rx:20
    style mq    fill:#e67e22,stroke:none,color:#fff,rx:20
    style minio fill:#d35400,stroke:none,color:#fff,rx:20
    style worker fill:#9b59b6,stroke:none,color:#fff,rx:20
    style beat   fill:#8e44ad,stroke:none,color:#fff,rx:20
    style godmode fill:#3498db,stroke:none,color:#fff,rx:20
    style ready   fill:#27ae60,stroke:none,color:#fff,rx:20
```
