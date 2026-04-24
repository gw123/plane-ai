# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from dataclasses import dataclass
from typing import Any

from django.db.models import Q

from plane.app.permissions.base import ROLE
from plane.db.models import Project, WorkspaceMember


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


class AgentToolRegistry:
    _tools = {
        ListProjectsTool.definition.name: ListProjectsTool,
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
