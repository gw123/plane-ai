# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.db import models

from .base import BaseModel
from .workspace import WorkspaceBaseModel


class AgentConversation(WorkspaceBaseModel):
    class Scope(models.TextChoices):
        WORKSPACE = "workspace", "Workspace"
        PROJECT = "project", "Project"

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    title = models.CharField(max_length=255, default="New conversation")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    last_message_at = models.DateTimeField(null=True, blank=True)

    @property
    def scope(self):
        return self.Scope.PROJECT if self.project_id else self.Scope.WORKSPACE

    class Meta:
        verbose_name = "Agent Conversation"
        verbose_name_plural = "Agent Conversations"
        db_table = "agent_conversations"
        ordering = ("-updated_at", "-created_at")


class AgentMessage(BaseModel):
    class Role(models.TextChoices):
        USER = "user", "User"
        ASSISTANT = "assistant", "Assistant"

    class Status(models.TextChoices):
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    conversation = models.ForeignKey(
        "db.AgentConversation",
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=20, choices=Role.choices)
    content = models.TextField(blank=True, default="")
    tool_calls = models.JSONField(null=True, blank=True)
    tool_results = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)

    class Meta:
        verbose_name = "Agent Message"
        verbose_name_plural = "Agent Messages"
        db_table = "agent_messages"
        ordering = ("created_at",)
