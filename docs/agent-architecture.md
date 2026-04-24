# Agent Architecture v0.1

> 目标：在 Plane 里落一个可持续演进的 Agent 能力
> 约束来源：`/Users/gaowei7/code/js/plane/docs/agent-contract.md`

---

## 1. 先回答目标

当前要做的不是“把一个大而全的 AI 聊天产品搬进 Plane”。

当前要做的是：

- 在 Plane 里建立一个可控的 Agent runtime
- 让它能稳定读写 Plane 的业务对象
- 让它的后端协议、前端呈现、工具边界都能持续演进
- 让后续每一轮开发都在收敛，而不是继续发散

所以这版架构追求的是：

- 边界清晰
- 依赖可替换
- 实现最薄
- 扩展点预留，但不提前实现

---

## 2. 架构决策

## 2.1 后端自有 runtime，不引入重型 Agent 框架

选择：

- 后端自己维护一个薄 runtime
- provider 走模型原生 tool calling
- runtime 只负责：
  - 组装上下文
  - 调模型
  - 执行 tool
  - 归一化事件
  - 持久化消息

不选重型 Agent 框架的原因：

- 现在需求边界很窄
- 业务工具都强依赖 Plane 自己的权限和 ORM
- 引入框架会让调试链路和协议边界变得更模糊
- 未来即使要接 LangGraph / Mastra，也应该挂在自有 adapter 后面，而不是先把产品架构绑死

## 2.2 前端引入 `assistant-ui`，但只用 runtime + primitives + tools

当前前端需要一个专门的 AI UI 库，否则自己拼会很快变丑、变散、变难维护。

选型结论：

- 选 `assistant-ui`
- 只用：
  - custom runtime
  - primitives
  - tool UI 能力
- 不用：
  - 它的默认整套视觉皮肤
  - Assistant Cloud
  - 强绑定 AI SDK backend 的 transport
  - 让它决定 Plane 的消息协议

原因：

- `assistant-ui` 官方文档明确支持 custom backend 和 `LocalRuntime` / `ExternalStoreRuntime`
- 它本身区分了 unstyled primitives 和现成组件，适合只接管 AI 交互层，不接管 Plane 的设计系统
- 当前 Plane Web 是 React Router 应用，不是 Next.js app router 项目
- `AI Elements` 官方方案是建立在 `shadcn/ui` + Next.js + AI SDK 的集成路径上，和当前 Plane 的前端边界不匹配

结论不是“为了接 AI 库而改 Plane”，而是“借一个足够薄的 AI UI runtime，加在 Plane 现有 UI 系统之上”。

---

## 3. 总体分层

```text
apps/web
  └─ Plane Agent UI
      └─ Runtime Adapter
          └─ Plane Agent SSE / REST API

apps/api
  └─ Plane Agent API
      └─ Agent Runtime
          ├─ Context Builder
          ├─ Provider Adapter
          ├─ Tool Registry
          ├─ Tool Executor
          └─ Event Stream Encoder

Plane Domain
  └─ Workspace / Project / Issue / Cycle / Member / Permission
```

核心原则：

- 上层不能穿透下层边界
- 前端只依赖 Plane API，不依赖 provider
- tool 不直接被前端调用，必须经过 runtime

---

## 4. 后端模块划分

建议目录：

```text
/Users/gaowei7/code/js/plane/apps/api/plane/agent/
├── api/
│   ├── serializers.py
│   ├── views.py
│   └── urls.py
├── application/
│   ├── conversation_service.py
│   ├── chat_service.py
│   ├── event_stream.py
│   └── context_builder.py
├── domain/
│   ├── contracts.py
│   └── exceptions.py
├── infrastructure/
│   ├── providers/
│   │   ├── base.py
│   │   └── anthropic.py
│   └── persistence/
│       └── repository.py
└── tools/
    ├── registry.py
    ├── base.py
    ├── issue_tools.py
    ├── cycle_tools.py
    └── project_tools.py
```

### 4.1 `api/`

职责：

- 提供 REST + SSE 入口
- 做参数解析和鉴权
- 不写业务编排逻辑

### 4.2 `application/`

职责：

- 编排一次 run 的完整生命周期
- 调用 provider、tool、持久化、事件流
- 这是 Agent 真正的“用例层”

### 4.3 `infrastructure/providers/`

职责：

- 把 Anthropic/OpenAI 等协议转成统一内部事件
- 屏蔽 provider 差异

约束：

- provider 返回的 block/event 不能外泄到 API 层

### 4.4 `tools/`

职责：

- 管理 tool 注册
- 管理 tool schema
- 执行具体业务逻辑

约束：

- 每个 tool 是最小独立单元
- 每个 tool 都必须复用 Plane 原有 service / permission，而不是另起一套业务逻辑

---

## 5. 前端模块划分

建议目录：

```text
/Users/gaowei7/code/js/plane/apps/web/core/components/agent/
├── runtime/
│   ├── agent-runtime-provider.tsx
│   ├── agent-model-adapter.ts
│   ├── message-converter.ts
│   └── tool-renderer-registry.tsx
├── thread/
│   ├── thread-root.tsx
│   ├── thread-header.tsx
│   ├── thread-list.tsx
│   ├── message-list.tsx
│   ├── message-item.tsx
│   └── composer.tsx
├── tool-ui/
│   ├── issue-created-card.tsx
│   ├── issue-list-card.tsx
│   ├── project-summary-card.tsx
│   └── index.ts
└── index.ts
```

配套基础包：

```text
/Users/gaowei7/code/js/plane/packages/services/src/ai/agent.service.ts
/Users/gaowei7/code/js/plane/packages/types/src/agent.ts
```

### 5.1 Runtime Adapter 是前端核心边界

前端不要把 `assistant-ui` 直接连到 provider 或第三方 transport。

正确做法：

- `agent.service.ts` 负责调用 Plane API
- `agent-model-adapter.ts` 把 Plane SSE 转成 `assistant-ui` runtime 可消费的数据
- `message-converter.ts` 负责 Plane Message 和 UI Message 双向映射

这样以后替换 UI 库、替换 provider、替换 SSE 协议时，只需要改 adapter 层。

### 5.2 `assistant-ui` 只解决“AI 交互壳”，不接管 Plane UI

保留原则：

- 样式继续走 Plane 的设计系统和 tailwind 语义层
- 卡片继续复用 Plane 现有 issue/project/cycle 视觉语言
- 新组件继续放在 Plane 的目录和包结构里

不接受：

- 把 `assistant-ui` 默认生成的整套视觉组件直接铺进项目
- 为了迁就 AI UI 库而重做页面样式结构

---

## 6. 扩展点怎么留，但现在不实现

用户已经明确排除了多 Agent、planner、RAG、长期记忆等能力。

所以“面向扩展”的正确做法不是提前把这些东西实现一遍，而是只冻结下面几个稳定接口。

## 6.1 Provider Adapter

```ts
type AgentProvider = {
  run(input: ProviderRunInput): AsyncIterable<ProviderEvent>;
};
```

现在只实现 `AnthropicAgentProvider`。

未来如果接 OpenAI / Azure / self-hosted model，只加 adapter，不改 API 契约。

## 6.2 Tool Registry

```ts
type AgentToolRegistry = {
  list(scope: "workspace" | "project"): AgentToolDefinition[];
  get(name: string): AgentToolDefinition | null;
  execute(name: string, input: unknown, ctx: AgentToolExecutionContext): Promise<AgentToolResult>;
};
```

未来加更多 tool，不改 runtime 主流程。

## 6.3 Context Builder

```ts
type AgentContextBuilder = {
  buildConversationContext(input: BuildContextInput): Promise<AgentContext>;
};
```

现在只做：

- workspace/project 基础信息
- 最近消息
- 最小业务上下文

未来加摘要、记忆、检索，都挂在这里，不污染其他层。

## 6.4 Frontend Tool Renderer Registry

```ts
type ToolRendererRegistry = Record<string, React.ComponentType<any>>;
```

现在只渲染少数高频工具卡片。

未来加新的 tool UI，只需要注册新的 renderer，不改 Thread 主结构。

---

## 7. 最小 Agent 开发单元怎么拆

之前一直返工，本质上不是“开发慢”，而是开发单元太大、边界没冻住、一个 PR 同时改了太多层。

后续一律按最小 Agent 开发单元推进。

## 7.1 定义

一个最小 Agent 开发单元必须满足：

- 只新增一个明确能力
- 只引入一层新的不确定性
- 有单独验收路径
- 做完后不会逼着后续推翻已有 schema

如果一个任务同时包含以下两类以上变化，就拆单：

- 新数据模型
- 新 API
- 新 stream 协议
- 新 tool
- 新 UI 卡片
- 新权限逻辑

## 7.2 交付模板

每个开发单元都必须写清楚：

- 目标能力
- 影响范围
- 输入输出样例
- 自动化测试
- 手工验收路径
- 明确不做什么

## 7.3 推荐拆分顺序

### U0 - 契约冻结

- 产物：contract + architecture 文档
- 验收：后续实现都能引用固定协议

### U1 - Conversation 数据模型 + CRUD

- 只做 conversation 和 message 持久化
- 不接模型，不接 SSE
- 验收：
  - 可创建 conversation
  - 可查询详情
  - 可删除 conversation

### U2 - Chat Endpoint Non-Streaming

- 只打通一次 user -> assistant 文本回复
- 先不做 tool
- 验收：
  - 提交消息后能拿到 assistant 回复
  - user / assistant message 都能持久化

### U3 - Provider Adapter

- 把 Anthropic 协议收敛到内部 runtime
- 不新增 UI
- 验收：
  - provider 错误能映射到标准错误码
  - 不向 API 层泄露 provider 原始结构

### U4 - 第一个只读 Tool

- 建议：`list_projects` 或 `search_issues`
- 先做只读，不做写操作
- 验收：
  - tool schema 冻结
  - tool call / result 能进消息持久化

### U5 - 标准 SSE

- 只做标准流式协议
- 不新增更多 tool
- 验收：
  - `run.started -> text.delta -> message.completed -> run.completed` 顺序稳定

### U6 - Frontend Runtime Adapter + Thread Shell

- 引入 `assistant-ui`
- 只做最基础 Thread、Message、Composer
- 不追求花哨 UI
- 验收：
  - 页面能发消息
  - 能流式展示文本
  - 能恢复历史对话

### U7 - 第一个写操作 Tool

- 建议：`create_issue`
- 验收：
  - 权限校验复用现有 Plane 逻辑
  - 成功和失败都能渲染结构化结果

### U8 - 高频 Tool Cards

- 只做 2-3 个高频卡片
- 建议：
  - `IssueCreatedCard`
  - `IssueListCard`
  - `ProjectSummaryCard`
- 验收：
  - UI 不靠 prompt 文本猜语义
  - 卡片数据完全来自稳定 `tool_result`

---

## 8. 如何避免再次发散

## 8.1 一次只推进一个不确定面

反例：

- 一次 PR 同时做 conversation model、SSE、tool registry、前端聊天页、卡片 UI

结果一定是：

- 问题定位困难
- 协议容易临时改来改去
- 验收标准不清楚

正确做法：

- 一次只打开一个不确定面

## 8.2 先只读，再写入

顺序必须是：

1. conversation
2. non-streaming chat
3. provider adapter
4. 只读 tool
5. SSE
6. 写入 tool

不要一上来就做 `create_issue`。

因为一旦写操作链路不稳，返工成本远高于只读链路。

## 8.3 先协议，再卡片

任何 tool card 的前提都是：

- `tool_name` 冻结
- `tool_result` schema 冻结
- 错误码冻结

如果这三件事没完成，不做卡片。

## 8.4 一层一层替换，不交叉替换

后续如果要换模型、换 UI 库、换 stream 实现，只允许在对应 adapter 边界内动。

不接受这种情况：

- 为了换 provider，改掉 message schema
- 为了换 UI 库，改掉后端事件协议

---

## 9. 前端库接入策略

## 9.1 接入目标

我们不是要“引入一个 AI 页面模板”。

我们要的是：

- 稳定的消息 runtime
- 稳定的 thread / composer 行为
- 稳定的 tool UI 接口

## 9.2 接入原则

- Plane 自己保留业务路由、页面结构、样式语义、服务层
- `assistant-ui` 只作为交互运行时
- 业务卡片和样式继续由 Plane 自己控制

## 9.3 页面形态

首版建议保持保守：

- 左侧：conversation list
- 中间：thread
- 底部：composer
- 工具结果以 Plane 风格卡片插入 message flow

不做：

- 花哨 generative dashboard
- 自动拼大面积分析看板
- 复杂拖拽式 agent workspace

---

## 10. 这版架构的成功标准

达到以下标准，说明架构方向对了：

- 后端协议没有 provider 泄漏
- 前端 UI 没有被 AI 库反向绑架
- 新增一个 tool 只需要改 registry + executor + renderer
- 新增一个 provider 只需要改 adapter
- 每个迭代单元都能单独验收
- 已上线单元不会因为后续扩展被整体推翻

如果做不到这些，说明边界还不够硬，需要继续收缩，而不是继续加功能。

---

## 11. 下一步只做什么

基于当前状态，下一步只建议做一个开发单元：

- U1：Conversation 数据模型 + CRUD

原因：

- 这是所有后续能力的基础
- 这是最便宜的验证单元
- 做完就能马上验证 scope、权限、列表、详情、删除的基本边界
- 即使后续 provider 或前端方案变化，U1 基本不需要返工

在 U1 做完之前，不建议开始前端库接入和 tool 开发。
