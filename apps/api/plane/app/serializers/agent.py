# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from rest_framework import serializers

from .base import BaseSerializer
from plane.db.models import AgentConversation, AgentMessage


class AgentMessageSerializer(BaseSerializer):
    id = serializers.UUIDField(read_only=True)
    conversation_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = AgentMessage
        fields = [
            "id",
            "conversation_id",
            "role",
            "content",
            "tool_calls",
            "tool_results",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class AgentConversationSerializer(BaseSerializer):
    id = serializers.UUIDField(read_only=True)
    workspace_id = serializers.UUIDField(read_only=True)
    project_id = serializers.UUIDField(read_only=True, allow_null=True)
    created_by_id = serializers.UUIDField(read_only=True, allow_null=True)
    scope = serializers.CharField(read_only=True)

    class Meta:
        model = AgentConversation
        fields = [
            "id",
            "workspace_id",
            "project_id",
            "scope",
            "title",
            "status",
            "created_by_id",
            "last_message_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "workspace_id",
            "project_id",
            "scope",
            "status",
            "created_by_id",
            "last_message_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "title": {
                "required": False,
                "allow_blank": True,
            }
        }


class AgentConversationDetailSerializer(AgentConversationSerializer):
    messages = AgentMessageSerializer(many=True, read_only=True)

    class Meta(AgentConversationSerializer.Meta):
        fields = [*AgentConversationSerializer.Meta.fields, "messages"]
        read_only_fields = [*AgentConversationSerializer.Meta.read_only_fields, "messages"]


class AgentChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField(allow_blank=False, trim_whitespace=True)
    client_request_id = serializers.CharField(required=False, allow_blank=False)
