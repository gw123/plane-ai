# Agent Contract v0.1

> 状态：冻结
> 生效日期：2026-04-24
> 目标：在 Plane 内落一个可持续演进的 Agent 能力，同时避免后续开发继续发散

---

## 1. 文档优先级

后续 Agent 开发如出现冲突，按下面优先级执行：

1. 本文档 `/Users/gaowei7/code/js/plane/docs/agent-contract.md`
2. 架构文档 `/Users/gaowei7/code/js/plane/docs/agent-architecture.md`
3. 方案文档 `/Users/gaowei7/code/js/plane/docs/agent-feature-plan.md`
4. 单个 PR 的实现细节

这份文档的职责不是描述“怎么实现”，而是冻结“什么不能变”。

---

## 2. 当前版本范围

### 2.1 必做范围

- 单 Agent，对话式交互
- 两种 scope：`workspace`、`project`
- 后端拥有 Agent runtime，前端只消费标准化结果
- 模型使用原生 tool calling
- 支持消息持久化
- 支持流式返回
- 支持最小一组 Plane 工具能力
- 支持基于现有 Plane 权限体系做 tool 执行校验

### 2.2 明确不做

以下能力不是现在的设计目标，后续如果要做，必须走新版本升级：

- 多 Agent
- planner / executor 双层架构
- RAG / 向量库
- 长期记忆
- 全自动任务编排
- 复杂 generative UI 框架接管前端

---

## 3. 约束原则

### 3.1 Runtime 归后端

- 前端不能直接感知 Anthropic/OpenAI 等 provider 的原始协议
- provider 特有字段只能存在于后端 adapter 层
- 前端只认 Plane 自己的消息、工具、SSE 事件协议

### 3.2 消息归一化

- 消息角色只允许 `user` 和 `assistant`
- tool 调用和 tool 结果挂在 `assistant` 消息上
- 不新增 `tool`、`tool_result`、`system` 等消息角色

### 3.3 协议只做增量演进

- `response` 字段可以新增
- `event.type` 可以新增
- 已有字段语义不能悄悄改变
- 破坏性变更必须升级版本并补迁移说明

### 3.4 先冻结数据语义，再做 UI

- 后端返回的 `tool_name`、`input`、`output` 语义未冻结前，不允许先做“漂亮卡片”
- 前端卡片必须依赖稳定 schema，而不是 prompt 文本猜测

---

## 4. 核心数据契约

## 4.1 AgentConversation

```ts
type AgentConversation = {
  id: string;
  workspace_id: string;
  project_id: string | null;
  scope: "workspace" | "project";
  title: string;
  status: "active" | "archived";
  created_by_id: string;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
};
```

约束：

- `project_id = null` 时，`scope` 必须为 `workspace`
- `project_id != null` 时，`scope` 必须为 `project`
- v0.1 中 conversation 只对创建者可见

## 4.2 AgentMessage

```ts
type AgentMessage = {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  tool_calls: AgentToolCall[] | null;
  tool_results: AgentToolResult[] | null;
  status: "completed" | "failed";
  created_at: string;
};
```

约束：

- `user` 消息必须满足：
  - `tool_calls = null`
  - `tool_results = null`
- `assistant` 消息允许：
  - 只有文本
  - 文本 + `tool_calls`
  - 文本 + `tool_calls` + `tool_results`
- 不允许把一次 run 拆成多条 tool message

## 4.3 AgentToolCall

```ts
type AgentToolCall = {
  call_id: string;
  tool_name: string;
  input: Record<string, unknown>;
  status: "pending" | "running" | "completed" | "failed";
};
```

## 4.4 AgentToolResult

```ts
type AgentToolResult = {
  call_id: string;
  tool_name: string;
  success: boolean;
  output: Record<string, unknown> | null;
  error: {
    code: string;
    message: string;
  } | null;
};
```

约束：

- `tool_results[*].call_id` 必须能回溯到 `tool_calls[*].call_id`
- tool 执行失败也必须产出结构化 `tool_result`
- tool 错误不能只塞进自由文本

---

## 5. API 契约

## 5.1 Conversation 列表

### Workspace scope

`GET /api/workspaces/{workspaceSlug}/agent/conversations/`

### Project scope

`GET /api/workspaces/{workspaceSlug}/projects/{projectId}/agent/conversations/`

返回：

```json
{
  "results": [
    {
      "id": "conv_123",
      "scope": "workspace",
      "title": "Create triage issues",
      "status": "active",
      "project_id": null,
      "last_message_at": "2026-04-24T08:30:00Z",
      "created_at": "2026-04-24T08:00:00Z"
    }
  ]
}
```

## 5.2 创建 Conversation

### Workspace scope

`POST /api/workspaces/{workspaceSlug}/agent/conversations/`

### Project scope

`POST /api/workspaces/{workspaceSlug}/projects/{projectId}/agent/conversations/`

请求：

```json
{
  "title": "New conversation"
}
```

约束：

- `title` 可选，后端允许兜底默认值
- 前端不能自行伪造 scope，scope 由 URL 决定

## 5.3 Conversation 详情

`GET /api/.../agent/conversations/{conversationId}/`

返回：

```json
{
  "conversation": {
    "id": "conv_123",
    "scope": "project",
    "workspace_id": "ws_1",
    "project_id": "proj_1",
    "title": "Sprint planning"
  },
  "messages": [
    {
      "id": "msg_u1",
      "role": "user",
      "content": "帮我列出本周高优 issue",
      "tool_calls": null,
      "tool_results": null,
      "status": "completed",
      "created_at": "2026-04-24T08:00:00Z"
    }
  ]
}
```

## 5.4 删除 Conversation

`DELETE /api/.../agent/conversations/{conversationId}/`

约束：

- v0.1 允许物理删除
- 后续如果改为软删除，API 语义不能变化

## 5.5 发送消息并开始一次 run

`POST /api/.../agent/conversations/{conversationId}/chat/`

请求：

```json
{
  "message": "帮我创建一个高优 bug，并分配给张三",
  "client_request_id": "optional-idempotency-key"
}
```

响应：

- `Content-Type: text/event-stream`
- 只返回标准化的 Plane Agent SSE 事件

---

## 6. SSE 事件契约

## 6.1 通用 envelope

每个事件的 `data` 必须是 JSON，并至少包含：

```ts
type AgentStreamEvent =
  | { type: "run.started"; run_id: string; conversation_id: string }
  | { type: "text.delta"; run_id: string; message_id: string; delta: string }
  | {
      type: "tool.call";
      run_id: string;
      message_id: string;
      call_id: string;
      tool_name: string;
      input: Record<string, unknown>;
    }
  | {
      type: "tool.result";
      run_id: string;
      message_id: string;
      call_id: string;
      tool_name: string;
      success: boolean;
      output: Record<string, unknown> | null;
      error: { code: string; message: string } | null;
    }
  | {
      type: "message.completed";
      run_id: string;
      message: AgentMessage;
    }
  | {
      type: "run.failed";
      run_id: string;
      error: { code: string; message: string; retryable: boolean };
    }
  | { type: "run.completed"; run_id: string };
```

## 6.2 顺序约束

一次正常 run 的事件顺序必须满足：

1. `run.started`
2. `text.delta` 0..n 次
3. `tool.call` / `tool.result` 0..n 组
4. `message.completed`
5. `run.completed`

失败时：

1. `run.started`
2. 若已有部分输出，可先出现 `text.delta`
3. `run.failed`

约束：

- `message.completed` 是消息持久化完成的信号
- 前端不能以最后一个 `text.delta` 作为完成判断
- `run.completed` 到达前，前端不得认为一次 run 已结束

---

## 7. Tool 契约

## 7.1 Tool 元数据

每个 tool 必须注册以下元数据：

```ts
type AgentToolDefinition = {
  name: string;
  description: string;
  scope: Array<"workspace" | "project">;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  readonly: boolean;
};
```

## 7.2 Tool 执行上下文

每次 tool 执行必须拿到统一上下文：

```ts
type AgentToolExecutionContext = {
  request_id: string;
  run_id: string;
  workspace_id: string;
  project_id: string | null;
  user_id: string;
};
```

## 7.3 Tool 返回约束

- 成功时必须返回结构化 `output`
- 失败时必须返回结构化 `error`
- 不能把 ORM 实体原样透出给前端
- 输出必须做最小字段投影

## 7.4 Tool 版本约束

- `tool_name` 一旦对前端开放，不能修改语义
- 输出 schema 如需调整，优先新增字段
- 如必须做破坏性变更，改为新 tool 或引入 `result_version`

---

## 8. 权限契约

- Conversation 访问权限继承当前登录用户
- Workspace scope tool 必须校验用户对 workspace 的访问权限
- Project scope tool 必须校验用户对 project 的访问权限
- 写操作 tool 必须复用 Plane 现有权限判断，不允许绕过
- tool 无权限时返回：

```json
{
  "code": "AGENT_TOOL_FORBIDDEN",
  "message": "You do not have permission to perform this action."
}
```

---

## 9. 错误码契约

v0.1 先冻结以下错误码：

| code                           | 含义                                   |
| ------------------------------ | -------------------------------------- |
| `AGENT_CONVERSATION_NOT_FOUND` | 对话不存在或无权访问                   |
| `AGENT_INVALID_SCOPE`          | URL scope 与 conversation scope 不一致 |
| `AGENT_PROVIDER_ERROR`         | 模型 provider 调用失败                 |
| `AGENT_PROVIDER_TIMEOUT`       | 模型调用超时                           |
| `AGENT_STREAM_ABORTED`         | 客户端主动中断                         |
| `AGENT_TOOL_NOT_FOUND`         | tool 未注册                            |
| `AGENT_TOOL_FORBIDDEN`         | tool 无权限执行                        |
| `AGENT_TOOL_VALIDATION_ERROR`  | tool 输入不合法                        |
| `AGENT_TOOL_EXECUTION_ERROR`   | tool 执行失败                          |

约束：

- SSE 内部错误必须落到上述错误码
- HTTP 层错误也必须使用同一套错误码

---

## 10. 非功能要求

- Conversation 创建、查询、删除必须可观测
- 每次 run 必须可追踪到 `request_id` 和 `run_id`
- tool 执行必须记录耗时和结果状态
- provider 原始响应只允许进入日志，不允许直接暴露到前端协议

---

## 11. 交付门禁

任何 Agent 相关 PR，至少满足以下条件：

1. 没有改坏本文档里的字段语义
2. 至少补一条对应契约测试
3. 至少给出一个手工验收路径
4. 如新增 tool，必须补 `input_schema` / `output_schema`
5. 如新增前端卡片，必须先有稳定 `tool_result` schema

---

## 12. 版本演进规则

### 允许的变更

- 新增只读 tool
- 新增写操作 tool
- 新增 SSE 事件类型
- 新增 message/tool 字段
- 新增 project/workspace 上下文信息

### 不允许的变更

- 把 `tool_result` 从 assistant message 挪成独立 message
- 修改 `role` 枚举
- 直接把 provider 原始协议暴露到前端
- 让前端依赖 prompt 文本解析业务含义

如果必须做以上变更，必须新建 `v0.2` 契约文档，而不是在 v0.1 上偷偷改。
