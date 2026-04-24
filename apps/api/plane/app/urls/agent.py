# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views import AgentConversationViewSet


urlpatterns = [
    path(
        "workspaces/<str:slug>/agent/conversations/",
        AgentConversationViewSet.as_view({"get": "list", "post": "create"}),
        name="workspace-agent-conversations",
    ),
    path(
        "workspaces/<str:slug>/agent/conversations/<uuid:pk>/",
        AgentConversationViewSet.as_view({"get": "retrieve", "delete": "destroy"}),
        name="workspace-agent-conversation-detail",
    ),
    path(
        "workspaces/<str:slug>/agent/conversations/<uuid:conversation_id>/chat/",
        AgentConversationViewSet.as_view({"post": "chat"}),
        name="workspace-agent-chat",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/agent/conversations/",
        AgentConversationViewSet.as_view({"get": "list", "post": "create"}),
        name="project-agent-conversations",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/agent/conversations/<uuid:pk>/",
        AgentConversationViewSet.as_view({"get": "retrieve", "delete": "destroy"}),
        name="project-agent-conversation-detail",
    ),
    path(
        "workspaces/<str:slug>/projects/<uuid:project_id>/agent/conversations/<uuid:conversation_id>/chat/",
        AgentConversationViewSet.as_view({"post": "chat"}),
        name="project-agent-chat",
    ),
]
