# Agent 功能集成方案

> 分支：`feat/add-agent`
> 级别：Workspace + Project 双层级
> 注意：如果本文件与 `/Users/gaowei7/code/js/plane/docs/agent-contract.md` 或 `/Users/gaowei7/code/js/plane/docs/agent-architecture.md` 冲突，以后两份文档为准。本文件保留为方案草稿，后续实现必须遵守冻结契约。

---

## 一、总体架构

```
用户 (Chat UI)
    │
    ▼
前端 SSE 流式接收
    │
    ▼
Django AgentChatEndpoint  ──→  Anthropic Claude API (Tool Use)
    │                                    │
    │                          ┌─────────▼──────────┐
    │                          │  Tool Executor      │
    │                          │  - create_issue     │
    │                          │  - list_issues      │
    │                          │  - search_issues    │
    │                          │  - update_issue     │
    │                          │  - list_projects    │
    │                          │  - create_cycle     │
    │                          └─────────┬──────────┘
    │                                    │
    │                          Plane ORM / DB
    │
    ▼
消息持久化 (AgentConversation / AgentMessage)
```

---

## 二、数据模型（后端）

### 2.1 文件位置

```
apps/api/plane/db/models/agent.py
```

### 2.2 模型定义

```python
class AgentConversation(BaseModel):
    workspace  = ForeignKey("db.Workspace", on_delete=CASCADE, related_name="agent_conversations")
    project    = ForeignKey("db.Project",   on_delete=CASCADE, related_name="agent_conversations",
                            null=True, blank=True)
    # project=null  → workspace scope
    # project=<id> → project scope

    created_by = ForeignKey(settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True,
                            related_name="agent_conversations")
    title      = CharField(max_length=255, default="New conversation")

    class Meta:
        ordering = ["-created_at"]


class AgentMessage(BaseModel):
    conversation = ForeignKey(AgentConversation, on_delete=CASCADE, related_name="messages")
    role         = CharField(max_length=20)      # "user" | "assistant" | "tool_result"
    content      = TextField(blank=True, default="")
    tool_calls   = JSONField(null=True, blank=True)   # Claude tool_use blocks
    tool_results = JSONField(null=True, blank=True)   # tool执行结果

    class Meta:
        ordering = ["created_at"]
```

### 2.3 注册到 `plane/db/models/__init__.py`

```python
from .agent import AgentConversation, AgentMessage
```

---

## 三、后端 API（后端）

### 3.1 目录结构

```
apps/api/plane/app/
├── views/
│   └── agent.py          ← 新建
└── urls/
    └── agent.py          ← 新建
```

注册到 `plane/app/views/__init__.py` 和 `plane/app/urls/__init__.py`。

### 3.2 URL 设计

```python
# plane/app/urls/agent.py

urlpatterns = [
    # ── Workspace scope ─────────────────────────────────────────────────────
    # 对话列表 & 新建
    path("workspaces/<str:slug>/agent/conversations/",
         AgentConversationViewset.as_view({"get": "list", "post": "create"}),
         name="workspace-agent-conversations"),

    # 对话详情 & 删除
    path("workspaces/<str:slug>/agent/conversations/<uuid:pk>/",
         AgentConversationViewset.as_view({"get": "retrieve", "delete": "destroy"}),
         name="workspace-agent-conversation-detail"),

    # 发送消息（SSE 流式响应）
    path("workspaces/<str:slug>/agent/conversations/<uuid:conversation_id>/chat/",
         AgentChatEndpoint.as_view(),
         name="workspace-agent-chat"),

    # ── Project scope ───────────────────────────────────────────────────────
    path("workspaces/<str:slug>/projects/<uuid:project_id>/agent/conversations/",
         AgentConversationViewset.as_view({"get": "list", "post": "create"}),
         name="project-agent-conversations"),

    path("workspaces/<str:slug>/projects/<uuid:project_id>/agent/conversations/<uuid:pk>/",
         AgentConversationViewset.as_view({"get": "retrieve", "delete": "destroy"}),
         name="project-agent-conversation-detail"),

    path("workspaces/<str:slug>/projects/<uuid:project_id>/agent/conversations/<uuid:conversation_id>/chat/",
         AgentChatEndpoint.as_view(),
         name="project-agent-chat"),
]
```

### 3.3 View 核心逻辑

```python
# plane/app/views/agent.py

class AgentConversationViewset(BaseViewSet):
    """通过 kwargs 中是否有 project_id 自动区分 scope"""

    def get_queryset(self):
        qs = AgentConversation.objects.filter(
            workspace__slug=self.kwargs["slug"],
            created_by=self.request.user,
        )
        if project_id := self.kwargs.get("project_id"):
            return qs.filter(project_id=project_id)
        return qs.filter(project__isnull=True)

    def perform_create(self, serializer):
        workspace = Workspace.objects.get(slug=self.kwargs["slug"])
        project_id = self.kwargs.get("project_id")
        serializer.save(
            workspace=workspace,
            project_id=project_id,
            created_by=self.request.user,
        )


class AgentChatEndpoint(BaseAPIView):
    """
    POST body: { "message": "帮我创建一个 bug issue" }
    响应：SSE text/event-stream
    """

    def post(self, request, slug, conversation_id, project_id=None):
        # 1. 持久化用户消息
        # 2. 加载历史消息构建 messages 列表
        # 3. 构建 system prompt（注入 workspace/project 上下文）
        # 4. 调用 Claude API（agentic loop）
        # 5. 工具调用：执行 → 返回结果给 Claude
        # 6. 流式 yield assistant 文本
        # 7. 持久化 assistant 消息 + tool_calls
        return StreamingHttpResponse(
            self._stream(request, slug, conversation_id, project_id),
            content_type="text/event-stream",
        )
```

### 3.4 Claude Tools 定义

```python
# plane/app/views/agent_tools.py

WORKSPACE_TOOLS = [
    {
        "name": "list_projects",
        "description": "列出 workspace 下所有项目",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "search_issues",
        "description": "全局搜索工作项",
        "input_schema": {
            "type": "object",
            "properties": {
                "query":      {"type": "string"},
                "project_id": {"type": "string", "description": "可选，限定项目"},
                "priority":   {"type": "string", "enum": ["urgent","high","medium","low","none"]},
                "state_type": {"type": "string", "enum": ["backlog","unstarted","started","completed","cancelled"]},
            },
            "required": ["query"],
        },
    },
    # ... create_issue, update_issue, create_cycle, get_project_summary ...
]

PROJECT_TOOLS = [
    # workspace tools 的子集 + 项目专属工具
    # list_states, list_labels, list_members 等
]
```

### 3.5 System Prompt 上下文注入

| Scope         | 注入内容                                                      |
| ------------- | ------------------------------------------------------------- |
| **Workspace** | 项目列表（id/name/identifier）、workspace 成员、最近活动摘要  |
| **Project**   | 项目名称、State 列表、Label 列表、Member 列表、当前活跃 Cycle |

---

## 四、前端路由（`apps/web`）

### 4.1 新增路由文件

```
app/(all)/[workspaceSlug]/(projects)/
└── agent/
    ├── layout.tsx
    ├── page.tsx                      ← 新对话 / 对话列表
    └── [conversationId]/
        └── page.tsx                  ← 历史对话详情

app/(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/
└── agent/
    ├── layout.tsx
    ├── page.tsx
    └── [conversationId]/
        └── page.tsx
```

### 4.2 路由注册（`app/routes/core.ts`）

在 workspace layout 块新增：

```ts
// Workspace Agent
layout("./(all)/[workspaceSlug]/(projects)/agent/layout.tsx", [
  route(":workspaceSlug/agent",
        "./(all)/[workspaceSlug]/(projects)/agent/page.tsx"),
  route(":workspaceSlug/agent/:conversationId",
        "./(all)/[workspaceSlug]/(projects)/agent/[conversationId]/page.tsx"),
]),
```

在 `[projectId]` layout 块新增：

```ts
// Project Agent
layout("./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/agent/layout.tsx", [
  route(":workspaceSlug/projects/:projectId/agent",
        "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/agent/page.tsx"),
  route(":workspaceSlug/projects/:projectId/agent/:conversationId",
        "./(all)/[workspaceSlug]/(projects)/projects/(detail)/[projectId]/agent/[conversationId]/page.tsx"),
]),
```

---

## 五、前端组件（`apps/web/core/components/agent/`）

### 5.1 组件结构

```
core/components/agent/
├── index.ts
├── agent-chat-root.tsx          ← 顶层容器，接收 scope props
├── conversation-sidebar.tsx     ← 历史对话列表（左侧面板）
├── conversation-header.tsx      ← 对话标题栏
├── message-list.tsx             ← 消息滚动列表
├── message-item.tsx             ← 单条消息（user / assistant）
├── message-input.tsx            ← 输入框 + 发送按钮
├── empty-state.tsx              ← 首次进入引导
└── tool-ui/                     ← Generative UI：每个 tool 的卡片组件
    ├── index.ts                 ← 统一导出所有 tool UI
    ├── create-issue-card.tsx    ← 创建 Issue 结果卡片
    ├── list-issues-card.tsx     ← Issue 列表结果卡片
    ├── search-issues-card.tsx   ← 搜索结果卡片
    ├── project-summary-card.tsx ← 项目统计看板卡片
    └── create-cycle-card.tsx    ← 创建 Cycle 结果卡片
```

### 5.2 核心组件接口

```tsx
// agent-chat-root.tsx —— 同一组件支持两种 scope
type AgentChatRootProps = {
  workspaceSlug: string;
  projectId?: string; // 有值 = project scope，无值 = workspace scope
  conversationId?: string; // 有值 = 恢复历史对话
};

export const AgentChatRoot = observer(({ workspaceSlug, projectId, conversationId }: AgentChatRootProps) => {
  // ...
});
```

### 5.3 Generative UI（Tool UI）

用 `makeAssistantToolUI` 把每个 tool 的结果映射为 React 组件，**替代纯文本展示**：

```tsx
// tool-ui/create-issue-card.tsx
import { makeAssistantToolUI } from "@assistant-ui/react";

export const CreateIssueTool = makeAssistantToolUI<
  { name: string; priority: string; project_id: string }, // tool input
  { id: string; sequence_id: string; state: string; name: string } // tool result
>({
  toolName: "create_issue",
  render: ({ args, result }) => {
    if (!result) {
      // 执行中：skeleton loading
      return <IssueCardSkeleton name={args.name} />;
    }
    // 执行完：Plane 风格 Issue 卡片
    return (
      <div className="rounded-lg border border-custom-border-200 bg-custom-background-100 p-3">
        <div className="flex items-center gap-2">
          <PriorityIcon priority={result.priority} />
          <span className="text-sm font-medium">{result.sequence_id}</span>
          <span className="text-sm text-custom-text-200">{result.name}</span>
        </div>
        <StateTag state={result.state} />
      </div>
    );
  },
});
```

各 tool 对应的卡片效果：

| Tool                  | 执行中状态         | 执行完状态                               |
| --------------------- | ------------------ | ---------------------------------------- |
| `create_issue`        | 灰色 skeleton 卡片 | Issue 卡片（优先级色块 + 序列号 + 状态） |
| `list_issues`         | 3 条 skeleton 行   | 可点击 Issue 列表（跳转到详情）          |
| `search_issues`       | 搜索动画           | 高亮关键词的结果卡片组                   |
| `get_project_summary` | 数字 skeleton      | 统计看板（完成率环形图 + 数字）          |
| `create_cycle`        | 灰色卡片           | Cycle 卡片（日期范围 + 颜色标记）        |

注册到 Thread：

```tsx
<AssistantRuntimeProvider runtime={runtime}>
  <Thread tools={[CreateIssueTool, ListIssuesTool, SearchIssuesTool, ProjectSummaryTool, CreateCycleTool]} />
</AssistantRuntimeProvider>
```

### 5.4 SSE 流式消费

```ts
// 通过 EventSource 或 fetch ReadableStream 消费 SSE
// 每个事件格式：
// data: {"type": "text_delta", "delta": "正在"}
// data: {"type": "text_delta", "delta": "创建..."}
// data: {"type": "tool_call", "tool_name": "create_issue", "input": {...}}
// data: {"type": "tool_result", "tool_name": "create_issue", "result": {...}}
// data: {"type": "done"}
```

---

## 五·五、交互场景 & Generative UI 卡片全景

### Issue / 工作项（最高频）

| #   | 用户说                                 | Tool                  | 卡片组件                                                          |
| --- | -------------------------------------- | --------------------- | ----------------------------------------------------------------- |
| 1   | "帮我创建一个 bug，分配给张三，高优"   | `create_issue`        | `IssueCreatedCard`（优先级色块 + 序列号 + 负责人头像 + 状态标签） |
| 2   | "把 BUG-42 优先级改为紧急"             | `update_issue`        | `IssueUpdatedCard`（before → after 对比，颜色变化）               |
| 3   | "把这些 issue 状态都改成 In Progress"  | `batch_update_issues` | `BatchOperationCard`（N 条列表 + 状态标签）                       |
| 4   | "搜索所有高优先级未完成的 issue"       | `search_issues`       | `IssueListCard`（可滚动列表，点击跳转）                           |
| 5   | "本周到期的 issue 有哪些"              | `list_issues`         | `IssueListCard`（按截止日分组，超期红色高亮）                     |
| 6   | "给 BUG-42 加一条评论：已修复，待验证" | `create_comment`      | `CommentCard`（头像 + 内容 + 时间戳）                             |
| 7   | "关联 BUG-42 和 BUG-55，设为 blocks"   | `create_relation`     | `RelationCard`（两个 Issue + 箭头连线）                           |
| 8   | "统计本项目有多少个 urgent issue"      | `count_issues`        | `StatsCard`（大数字 + 优先级色块）                                |
| 9   | "我今天要做什么"                       | `list_issues`         | `DailyPlanCard`（分优先级 checklist 样式）                        |
| 10  | "帮我找出所有超期未完成的 issue"       | `search_issues`       | `IssueListCard`（红色高亮 + 超期天数 badge）                      |

### Cycle / 迭代

| #   | 用户说                       | Tool                     | 卡片组件                                                    |
| --- | ---------------------------- | ------------------------ | ----------------------------------------------------------- |
| 11  | "创建下周的迭代，5.1 到 5.7" | `create_cycle`           | `CycleCreatedCard`（名称 + 日期范围 + 状态徽章）            |
| 12  | "当前迭代进展怎么样"         | `get_cycle_progress`     | `CycleProgressCard`（完成率环形图 + 各状态数量 + 剩余天数） |
| 13  | "把 BUG-42 加入当前迭代"     | `add_issue_to_cycle`     | `CycleUpdatedCard`（Cycle 名 + Issue 序列号）               |
| 14  | "列出所有未完成的迭代"       | `list_cycles`            | `CycleListCard`（状态色块 + 日期 + 进度条）                 |
| 15  | "当前迭代里谁的 issue 最多"  | `get_cycle_member_stats` | `MemberWorkloadCard`（头像 + 数量条形图）                   |
| 16  | "当前迭代的 burndown 怎么样" | `get_cycle_burndown`     | `BurndownCard`（折线图：理想线 vs 实际线）                  |

### Module / 模块

| #   | 用户说                              | Tool                  | 卡片组件                                       |
| --- | ----------------------------------- | --------------------- | ---------------------------------------------- |
| 17  | "创建一个模块叫「支付重构」"        | `create_module`       | `ModuleCreatedCard`（名称 + 状态 + Lead 头像） |
| 18  | "把登录相关的 issue 都加入支付模块" | `batch_add_to_module` | `BatchOperationCard`（Module + N 条 issue）    |
| 19  | "「支付重构」模块完成度多少"        | `get_module_progress` | `ModuleProgressCard`（完成率 + 状态分布）      |
| 20  | "列出所有进行中的模块"              | `list_modules`        | `ModuleListCard`（状态色块 + 日期 + 负责人）   |

### Project / 项目

| #   | 用户说                        | Tool                   | 卡片组件                                                         |
| --- | ----------------------------- | ---------------------- | ---------------------------------------------------------------- |
| 21  | "这个项目整体状态怎么样"      | `get_project_summary`  | `ProjectSummaryCard`（总 issue 数 + 各状态分布 + 本周新增/完成） |
| 22  | "列出我参与的所有项目"        | `list_projects`        | `ProjectListCard`（emoji + 名称 + identifier + 成员数）          |
| 23  | "哪个项目的 backlog 积压最多" | `list_projects` + 统计 | `ProjectCompareCard`（横向条形图，按积压数排序）                 |
| 24  | "给「前端」项目添加成员王五"  | `add_project_member`   | `MemberAddedCard`（头像 + 邮箱 + 角色徽章）                      |

### 跨实体 / 分析类

| #   | 用户说                                  | Tool                     | 卡片组件                                         |
| --- | --------------------------------------- | ------------------------ | ------------------------------------------------ |
| 25  | "本周所有项目的完成情况汇总"            | `get_project_summary` ×N | `ProjectSummaryCard`（多项目对比，进度条）       |
| 26  | "张三目前有多少未完成的 issue"          | `list_issues`            | `MemberWorkloadCard`（头像 + 数量 + 优先级分布） |
| 27  | "最近 7 天新增了多少 issue，解决了多少" | `get_analytics`          | `TrendChartCard`（新增 vs 关闭折线图，日粒度）   |

### 优先实现的卡片（按阶段）

```
Phase 1 MVP（7 个卡片，覆盖 ~70% 日常使用）
├── IssueCreatedCard       场景 1
├── IssueUpdatedCard       场景 2、3
├── IssueListCard          场景 4、5、10
├── ProjectSummaryCard     场景 21、25
├── CycleProgressCard      场景 12、16
├── BatchOperationCard     场景 3、18
└── StatsCard              场景 8

Phase 2（8 个卡片）
├── CycleCreatedCard       场景 11
├── CycleListCard          场景 14
├── ModuleProgressCard     场景 19
├── MemberWorkloadCard     场景 15、26
├── TrendChartCard         场景 27
├── RelationCard           场景 7
├── DailyPlanCard          场景 9
└── BurndownCard           场景 16

Phase 3（4 个卡片）
├── CommentCard            场景 6
├── ProjectListCard        场景 22
├── ProjectCompareCard     场景 23
└── ModuleListCard         场景 20
```

---

## 六、导航入口

### 6.1 Workspace 侧边栏（`ce/components/app-rail/app-rail-hoc.tsx`）

在 `dockItems` 数组新增 Agent 入口：

```ts
{
  label: "Agent",
  icon: <SparklesIcon className="size-5" />,
  href: `/${workspaceSlug}/agent`,
  isActive: pathname.includes(`/${workspaceSlug}/agent`),
  shouldRender: true,
}
```

### 6.2 Project Tab 导航（`ce/components/navigations/use-navigation-items.ts`）

在 `baseNavigation` 数组新增：

```ts
{
  i18n_key: "sidebar.agent",
  key: "agent",
  name: "Agent",
  href: `/${workspaceSlug}/projects/${projectId}/agent`,
  icon: SparklesIcon,
  access: [EUserPermissions.ADMIN, EUserPermissions.MEMBER, EUserPermissions.GUEST],
  shouldRender: true,
  sortOrder: 7,
}
```

---

## 七、共享 Package

### 7.1 `packages/services/src/ai/agent.service.ts`（新建）

```ts
export class AgentService extends APIService {
  // 对话管理
  async listConversations(workspaceSlug: string, projectId?: string): Promise<IAgentConversation[]>;
  async createConversation(workspaceSlug: string, projectId?: string): Promise<IAgentConversation>;
  async deleteConversation(workspaceSlug: string, conversationId: string, projectId?: string): Promise<void>;

  // 发送消息（返回 ReadableStream for SSE）
  async sendMessage(
    workspaceSlug: string,
    conversationId: string,
    message: string,
    projectId?: string
  ): Promise<ReadableStream>;
}
```

### 7.2 `packages/types/src/agent.ts`（新建）

```ts
export interface IAgentConversation {
  id: string;
  title: string;
  workspace: string;
  project: string | null;
  created_at: string;
  created_by: string;
}

export interface IAgentMessage {
  id: string;
  conversation: string;
  role: "user" | "assistant";
  content: string;
  tool_calls: IToolCall[] | null;
  tool_results: IToolResult[] | null;
  created_at: string;
}

export interface IToolCall {
  tool_name: string;
  input: Record<string, unknown>;
}

export interface IToolResult {
  tool_name: string;
  result: Record<string, unknown>;
  success: boolean;
}
```

---

## 八、实现路径（分阶段）

### Phase 1：最小可用版本（MVP）

- [ ] 后端：`AgentConversation` + `AgentMessage` models + migration
- [ ] 后端：Conversation CRUD API（非流式）
- [ ] 后端：`AgentChatEndpoint` 非流式版（先 POST 返回 JSON）
- [ ] 后端：实现 `create_issue` / `list_issues` / `search_issues` 三个 tool
- [ ] 前端：`packages/types/src/agent.ts` 类型定义
- [ ] 前端：`packages/services/src/ai/agent.service.ts`
- [ ] 前端：`AgentChatRoot` + `MessageList` + `MessageInput` 基础 UI
- [ ] 前端：Workspace 路由 + 侧边栏入口

### Phase 2：体验提升

- [ ] 后端：SSE 流式响应
- [ ] 前端：SSE 流式渲染（打字机效果）
- [ ] 前端：`ToolCallCard` 操作结果可视化
- [ ] 前端：Project 路由 + Tab 导航入口
- [ ] 后端：`update_issue` / `create_cycle` / `get_project_summary` tools

### Phase 3：深度集成

- [ ] 后端：历史消息上下文（多轮对话 token 管理）
- [ ] 前端：历史对话列表 + 恢复对话
- [ ] 前端：对话内引用卡片（点击 Issue 卡片跳转详情）
- [ ] 后端：权限控制（Agent tool 执行前校验用户对 project 的权限）

---

## 九、关键约束

| 约束              | 处理方式                                             |
| ----------------- | ---------------------------------------------------- |
| Anthropic API Key | 存 Django `settings.ANTHROPIC_API_KEY`，环境变量注入 |
| 权限隔离          | Tool 执行前复用 `ProjectMemberPermission` 校验       |
| Token 上限        | 历史消息超过 N 条时做摘要压缩（Phase 3）             |
| 流式超时          | Nginx/proxy 配置 `proxy_read_timeout 120s`           |
| 并发              | 每个用户同时只允许一个活跃 chat stream               |
