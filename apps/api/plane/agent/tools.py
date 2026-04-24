# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from dataclasses import dataclass
from typing import Any
from html import escape

from django.db.models import Q

from plane.app.issue_creation import enqueue_issue_created_activity
from plane.app.serializers import IssueCreateSerializer
from plane.app.permissions.base import ROLE
from plane.db.models import Project, ProjectMember, WorkspaceMember


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

        issue = serializer.save(created_by_id=ctx.user_id, updated_by_id=ctx.user_id)
        issue = (
            issue.__class__.objects.select_related("project", "state")
            .get(id=issue.id)
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


class AgentToolRegistry:
    _tools = {
        ListProjectsTool.definition.name: ListProjectsTool,
        CreateIssueTool.definition.name: CreateIssueTool,
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
