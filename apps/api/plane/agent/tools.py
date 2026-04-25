# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from dataclasses import dataclass
from typing import Any
from html import escape

from django.db import transaction
from django.db.models import Q

from plane.app.issue_creation import enqueue_issue_created_activity
from plane.app.serializers import IssueCreateSerializer
from plane.app.permissions.base import ROLE
from plane.db.models import Issue, Project, ProjectMember, State, WorkspaceMember
from plane.utils.issue_search import search_issues


@dataclass(frozen=True)
class AgentToolDefinition:
    name: str
    description: str
    scope: list[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    readonly: bool

    def to_provider_tool(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


@dataclass(frozen=True)
class AgentToolExecutionContext:
    request_id: str
    run_id: str
    workspace_id: str
    project_id: str | None
    user_id: str

    @property
    def scope(self) -> str:
        return "project" if self.project_id else "workspace"


@dataclass(frozen=True)
class AgentToolExecutionResult:
    success: bool
    output: dict[str, Any] | None
    error: dict[str, str] | None


class ListProjectsTool:
    definition = AgentToolDefinition(
        name="list_projects",
        description="List projects in the current workspace that are visible to the current user.",
        scope=["workspace"],
        input_schema={
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "projects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "identifier": {"type": "string"},
                            "name": {"type": "string"},
                            "emoji": {"type": ["string", "null"]},
                            "logo_props": {"type": ["object", "null"]},
                            "is_archived": {"type": "boolean"},
                        },
                        "required": [
                            "id",
                            "identifier",
                            "name",
                            "emoji",
                            "logo_props",
                            "is_archived",
                        ],
                    },
                },
            },
            "required": ["count", "projects"],
        },
        readonly=True,
    )

    @classmethod
    def execute(cls, input_data: dict[str, Any], ctx: AgentToolExecutionContext) -> AgentToolExecutionResult:
        if ctx.scope != "workspace":
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_FORBIDDEN",
                    "message": "This tool is only available in workspace conversations.",
                },
            )

        if input_data:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_VALIDATION_ERROR",
                    "message": "list_projects does not accept any input.",
                },
            )

        membership = WorkspaceMember.objects.filter(
            workspace_id=ctx.workspace_id,
            member_id=ctx.user_id,
            is_active=True,
        ).only("role").first()
        if membership is None:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_FORBIDDEN",
                    "message": "You do not have permission to perform this action.",
                },
            )

        projects = Project.objects.filter(workspace_id=ctx.workspace_id)
        if membership.role == ROLE.GUEST.value:
            projects = projects.filter(
                project_projectmember__member_id=ctx.user_id,
                project_projectmember__is_active=True,
            )
        elif membership.role == ROLE.MEMBER.value:
            projects = projects.filter(
                Q(
                    project_projectmember__member_id=ctx.user_id,
                    project_projectmember__is_active=True,
                )
                | Q(network=2)
            )

        items = [
            {
                "id": str(project["id"]),
                "identifier": project["identifier"],
                "name": project["name"],
                "emoji": project["emoji"],
                "logo_props": project["logo_props"],
                "is_archived": project["archived_at"] is not None,
            }
            for project in projects.order_by("name")
            .values("id", "identifier", "name", "emoji", "logo_props", "archived_at")
            .distinct()
        ]
        return AgentToolExecutionResult(
            success=True,
            output={
                "count": len(items),
                "projects": items,
            },
            error=None,
        )


class CreateIssueTool:
    SUPPORTED_INPUT_KEYS = frozenset({"name", "description", "priority"})

    definition = AgentToolDefinition(
        name="create_issue",
        description="Create a new issue in the current project.",
        scope=["project"],
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low", "none"]},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "project_id": {"type": "string"},
                "project_identifier": {"type": "string"},
                "display_id": {"type": "string"},
                "sequence_id": {"type": "integer"},
                "name": {"type": "string"},
                "priority": {"type": "string"},
                "state": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "group": {"type": "string"},
                        "color": {"type": "string"},
                    },
                    "required": ["id", "name", "group", "color"],
                },
            },
            "required": [
                "id",
                "project_id",
                "project_identifier",
                "display_id",
                "sequence_id",
                "name",
                "priority",
                "state",
            ],
        },
        readonly=False,
    )

    @staticmethod
    def _extract_validation_message(errors: Any) -> str:
        if isinstance(errors, dict):
            first_value = next(iter(errors.values()), None)
            return CreateIssueTool._extract_validation_message(first_value)
        if isinstance(errors, list) and errors:
            return CreateIssueTool._extract_validation_message(errors[0])
        if isinstance(errors, str):
            return errors
        return "Invalid create_issue input."

    @staticmethod
    def _build_description_html(description: str | None) -> str | None:
        if not description:
            return None
        escaped = escape(description).replace("\n", "<br />")
        return f"<p>{escaped}</p>"

    @classmethod
    def _validate_supported_input(cls, input_data: dict[str, Any]) -> AgentToolExecutionResult | None:
        unsupported_keys = sorted(set(input_data.keys()) - cls.SUPPORTED_INPUT_KEYS)
        if not unsupported_keys:
            return None

        unsupported_fields = ", ".join(unsupported_keys)
        return AgentToolExecutionResult(
            success=False,
            output=None,
            error={
                "code": "AGENT_TOOL_VALIDATION_ERROR",
                "message": (
                    f"Unsupported create_issue input fields: {unsupported_fields}. "
                    "Only name, description, priority are supported."
                ),
            },
        )

    @staticmethod
    def _build_missing_state_error() -> dict[str, str]:
        return {
            "code": "AGENT_TOOL_EXECUTION_ERROR",
            "message": "This project has no available issue state. Configure a non-triage state before using create_issue.",
        }

    @staticmethod
    def _has_project_write_access(ctx: AgentToolExecutionContext) -> bool:
        has_allowed_role = ProjectMember.objects.filter(
            member_id=ctx.user_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            role__in=[ROLE.ADMIN.value, ROLE.MEMBER.value],
            is_active=True,
        ).exists()
        if has_allowed_role:
            return True

        return (
            ProjectMember.objects.filter(
                member_id=ctx.user_id,
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                is_active=True,
            ).exists()
            and WorkspaceMember.objects.filter(
                member_id=ctx.user_id,
                workspace_id=ctx.workspace_id,
                role=ROLE.ADMIN.value,
                is_active=True,
            ).exists()
        )

    @classmethod
    def execute(cls, input_data: dict[str, Any], ctx: AgentToolExecutionContext) -> AgentToolExecutionResult:
        if ctx.scope != "project" or ctx.project_id is None:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_FORBIDDEN",
                    "message": "This tool is only available in project conversations.",
                },
            )

        if not cls._has_project_write_access(ctx):
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_FORBIDDEN",
                    "message": "You do not have permission to create issues in this project.",
                },
            )

        unsupported_input_result = cls._validate_supported_input(input_data)
        if unsupported_input_result is not None:
            return unsupported_input_result

        project = Project.objects.filter(id=ctx.project_id, workspace_id=ctx.workspace_id).first()
        if project is None:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_NOT_FOUND",
                    "message": "Project not found.",
                },
            )

        if not State.objects.filter(project_id=project.id).exists():
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error=cls._build_missing_state_error(),
            )

        payload = {
            "name": input_data.get("name"),
            "priority": input_data.get("priority", "none"),
        }
        description_html = cls._build_description_html(input_data.get("description"))
        if description_html is not None:
            payload["description_html"] = description_html

        serializer = IssueCreateSerializer(
            data=payload,
            context={
                "project_id": str(project.id),
                "workspace_id": str(project.workspace_id),
                "default_assignee_id": project.default_assignee_id,
            },
        )
        if not serializer.is_valid():
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_VALIDATION_ERROR",
                    "message": cls._extract_validation_message(serializer.errors),
                },
            )

        try:
            with transaction.atomic():
                issue = serializer.save(created_by_id=ctx.user_id, updated_by_id=ctx.user_id)
                issue = (
                    issue.__class__.objects.select_related("project", "state").get(id=issue.id)
                )
                if issue.state is None:
                    raise ValueError
        except ValueError:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error=cls._build_missing_state_error(),
            )

        enqueue_issue_created_activity(
            requested_data=input_data,
            actor_id=ctx.user_id,
            issue_id=str(issue.id),
            project_id=str(project.id),
        )

        return AgentToolExecutionResult(
            success=True,
            output={
                "id": str(issue.id),
                "project_id": str(issue.project_id),
                "project_identifier": issue.project.identifier,
                "display_id": f"{issue.project.identifier}-{issue.sequence_id}",
                "sequence_id": issue.sequence_id,
                "name": issue.name,
                "priority": issue.priority,
                "state": {
                    "id": str(issue.state_id),
                    "name": issue.state.name,
                    "group": issue.state.group,
                    "color": issue.state.color,
                },
            },
            error=None,
        )


class ListIssuesTool:
    SUPPORTED_INPUT_KEYS = frozenset({"query", "priority", "state_group", "assignee_id", "limit"})
    DEFAULT_LIMIT = 5
    MAX_LIMIT = 20
    VALID_PRIORITIES = frozenset({"urgent", "high", "medium", "low", "none"})
    VALID_STATE_GROUPS = frozenset({"backlog", "unstarted", "started", "completed", "cancelled"})

    definition = AgentToolDefinition(
        name="list_issues",
        description=(
            "List issues in the current project. Use this when the user asks which issues exist, "
            "what is open, what is due soon, or wants a shortlist. Supports optional filtering by "
            "title/query text, priority, state group, assignee, and limit."
        ),
        scope=["project"],
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "priority": {"type": "string", "enum": ["urgent", "high", "medium", "low", "none"]},
                "state_group": {
                    "type": "string",
                    "enum": ["backlog", "unstarted", "started", "completed", "cancelled"],
                },
                "assignee_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "count": {"type": "integer"},
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "display_id": {"type": "string"},
                            "name": {"type": "string"},
                            "priority": {"type": "string"},
                            "start_date": {"type": ["string", "null"]},
                            "target_date": {"type": ["string", "null"]},
                            "state": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "name": {"type": "string"},
                                    "group": {"type": "string"},
                                    "color": {"type": "string"},
                                },
                                "required": ["id", "name", "group", "color"],
                            },
                        },
                        "required": [
                            "id",
                            "display_id",
                            "name",
                            "priority",
                            "start_date",
                            "target_date",
                            "state",
                        ],
                    },
                },
            },
            "required": ["count", "issues"],
        },
        readonly=True,
    )

    @classmethod
    def _build_validation_error(cls, message: str) -> AgentToolExecutionResult:
        return AgentToolExecutionResult(
            success=False,
            output=None,
            error={
                "code": "AGENT_TOOL_VALIDATION_ERROR",
                "message": message,
            },
        )

    @classmethod
    def _validate_supported_input(cls, input_data: dict[str, Any]) -> AgentToolExecutionResult | None:
        unsupported_keys = sorted(set(input_data.keys()) - cls.SUPPORTED_INPUT_KEYS)
        if not unsupported_keys:
            return None

        unsupported_fields = ", ".join(unsupported_keys)
        return cls._build_validation_error(
            f"Unsupported list_issues input fields: {unsupported_fields}. "
            "Only query, priority, state_group, assignee_id, limit are supported."
        )

    @classmethod
    def _normalize_input(cls, input_data: dict[str, Any]) -> tuple[dict[str, Any] | None, AgentToolExecutionResult | None]:
        unsupported_input_result = cls._validate_supported_input(input_data)
        if unsupported_input_result is not None:
            return None, unsupported_input_result

        normalized: dict[str, Any] = {"limit": cls.DEFAULT_LIMIT}

        query = input_data.get("query")
        if query is not None:
            if not isinstance(query, str) or not query.strip():
                return None, cls._build_validation_error("list_issues query must be a non-empty string.")
            normalized["query"] = query.strip()

        priority = input_data.get("priority")
        if priority is not None:
            if not isinstance(priority, str) or priority not in cls.VALID_PRIORITIES:
                return None, cls._build_validation_error(
                    "list_issues priority must be one of urgent, high, medium, low, none."
                )
            normalized["priority"] = priority

        state_group = input_data.get("state_group")
        if state_group is not None:
            if not isinstance(state_group, str) or state_group not in cls.VALID_STATE_GROUPS:
                return None, cls._build_validation_error(
                    "list_issues state_group must be one of backlog, unstarted, started, completed, cancelled."
                )
            normalized["state_group"] = state_group

        assignee_id = input_data.get("assignee_id")
        if assignee_id is not None:
            if not isinstance(assignee_id, str) or not assignee_id.strip():
                return None, cls._build_validation_error("list_issues assignee_id must be a non-empty string.")
            normalized["assignee_id"] = assignee_id.strip()

        limit = input_data.get("limit")
        if limit is not None:
            if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1 or limit > cls.MAX_LIMIT:
                return None, cls._build_validation_error("list_issues limit must be an integer between 1 and 20.")
            normalized["limit"] = limit

        return normalized, None

    @staticmethod
    def _has_project_read_access(ctx: AgentToolExecutionContext) -> bool:
        if ctx.project_id is None:
            return False

        has_project_membership = ProjectMember.objects.filter(
            member_id=ctx.user_id,
            workspace_id=ctx.workspace_id,
            project_id=ctx.project_id,
            is_active=True,
        ).exists()
        if has_project_membership:
            return True

        return WorkspaceMember.objects.filter(
            member_id=ctx.user_id,
            workspace_id=ctx.workspace_id,
            role=ROLE.ADMIN.value,
            is_active=True,
        ).exists()

    @classmethod
    def execute(cls, input_data: dict[str, Any], ctx: AgentToolExecutionContext) -> AgentToolExecutionResult:
        if ctx.scope != "project" or ctx.project_id is None:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_FORBIDDEN",
                    "message": "This tool is only available in project conversations.",
                },
            )

        if not cls._has_project_read_access(ctx):
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_FORBIDDEN",
                    "message": "You do not have permission to list issues in this project.",
                },
            )

        normalized_input, validation_error = cls._normalize_input(input_data)
        if validation_error is not None:
            return validation_error

        project = Project.objects.filter(id=ctx.project_id, workspace_id=ctx.workspace_id).first()
        if project is None:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_NOT_FOUND",
                    "message": "Project not found.",
                },
            )

        issues = (
            Issue.issue_objects.filter(
                workspace_id=ctx.workspace_id,
                project_id=ctx.project_id,
                is_draft=False,
                state__isnull=False,
            )
            .select_related("project", "state")
            .distinct()
        )

        query = normalized_input.get("query")
        if query:
            issues = search_issues(query, issues)

        priority = normalized_input.get("priority")
        if priority:
            issues = issues.filter(priority=priority)

        state_group = normalized_input.get("state_group")
        if state_group:
            issues = issues.filter(state__group=state_group)

        assignee_id = normalized_input.get("assignee_id")
        if assignee_id:
            issues = issues.filter(
                issue_assignee__assignee_id=assignee_id,
                issue_assignee__deleted_at__isnull=True,
            )

        issues = issues.distinct()
        total_count = issues.count()
        limited_issues = issues.order_by("sequence_id")[: normalized_input["limit"]]

        return AgentToolExecutionResult(
            success=True,
            output={
                "count": total_count,
                "issues": [
                    {
                        "id": str(issue.id),
                        "display_id": f"{issue.project.identifier}-{issue.sequence_id}",
                        "name": issue.name,
                        "priority": issue.priority,
                        "start_date": issue.start_date.isoformat() if issue.start_date else None,
                        "target_date": issue.target_date.isoformat() if issue.target_date else None,
                        "state": {
                            "id": str(issue.state_id),
                            "name": issue.state.name,
                            "group": issue.state.group,
                            "color": issue.state.color,
                        },
                    }
                    for issue in limited_issues
                ],
            },
            error=None,
        )


class AgentToolRegistry:
    _tools = {
        ListProjectsTool.definition.name: ListProjectsTool,
        CreateIssueTool.definition.name: CreateIssueTool,
        ListIssuesTool.definition.name: ListIssuesTool,
    }

    @classmethod
    def list(cls, scope: str) -> list[AgentToolDefinition]:
        return [
            tool.definition
            for tool in cls._tools.values()
            if scope in tool.definition.scope
        ]

    @classmethod
    def get(cls, name: str):
        return cls._tools.get(name)

    @classmethod
    def execute(cls, name: str, input_data: dict[str, Any], ctx: AgentToolExecutionContext) -> AgentToolExecutionResult:
        tool = cls.get(name)
        if tool is None:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_NOT_FOUND",
                    "message": f"Tool '{name}' is not registered.",
                },
            )

        try:
            return tool.execute(input_data, ctx)
        except Exception:
            return AgentToolExecutionResult(
                success=False,
                output=None,
                error={
                    "code": "AGENT_TOOL_EXECUTION_ERROR",
                    "message": f"Tool '{name}' failed to execute.",
                },
            )
