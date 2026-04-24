# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from uuid import uuid4

from django.db import transaction
from django.db.models.functions import Coalesce
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.response import Response

from plane.agent.chat import (
    AgentChatConfigurationError,
    AgentChatContext,
    AgentChatError,
    AgentChatResult,
    AgentChatService,
)
from plane.agent.stream import encode_sse_event
from plane.app.serializers import AgentChatRequestSerializer, AgentConversationSerializer, AgentMessageSerializer
from plane.app.views.base import BaseViewSet
from plane.db.models import AgentConversation, AgentMessage, Project, ProjectMember, Workspace, WorkspaceMember


class AgentConversationViewSet(BaseViewSet):
    model = AgentConversation

    def get_serializer_class(self):
        return AgentConversationSerializer

    def _has_scope_access(self):
        if self.project_id:
            return ProjectMember.objects.filter(
                workspace__slug=self.workspace_slug,
                project_id=self.project_id,
                member=self.request.user,
                is_active=True,
            ).exists()

        return WorkspaceMember.objects.filter(
            workspace__slug=self.workspace_slug,
            member=self.request.user,
            is_active=True,
        ).exists()

    def _scope_denied_response(self):
        return Response(
            {"error": "You don't have the required permissions."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def get_queryset(self):
        queryset = (
            AgentConversation.objects.filter(
                workspace__slug=self.workspace_slug,
                created_by=self.request.user,
            )
            .select_related("workspace", "project")
            .prefetch_related("messages")
        )
        queryset = queryset.order_by(Coalesce("last_message_at", "created_at").desc(), "-created_at")

        if self.project_id:
            return queryset.filter(project_id=self.project_id)

        return queryset.filter(project__isnull=True)

    def get_chat_queryset(self):
        queryset = AgentConversation.objects.filter(
            workspace__slug=self.workspace_slug,
            created_by=self.request.user,
        ).select_related("workspace", "project")

        if self.project_id:
            return queryset.filter(project_id=self.project_id)

        return queryset.filter(project__isnull=True)

    def list(self, request, slug, project_id=None):
        if not self._has_scope_access():
            return self._scope_denied_response()

        serializer = self.get_serializer(self.get_queryset(), many=True)
        return Response({"results": serializer.data}, status=status.HTTP_200_OK)

    def create(self, request, slug, project_id=None):
        if not self._has_scope_access():
            return self._scope_denied_response()

        workspace = get_object_or_404(Workspace, slug=slug)
        project = None

        if project_id:
            project = get_object_or_404(Project, pk=project_id, workspace__slug=slug)

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        conversation = AgentConversation(
            workspace=workspace,
            project=project,
            title=serializer.validated_data.get("title") or AgentConversation._meta.get_field("title").default,
        )
        conversation.save(created_by_id=request.user.id)
        return Response(AgentConversationSerializer(conversation).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, slug, pk, project_id=None):
        if not self._has_scope_access():
            return self._scope_denied_response()

        conversation = get_object_or_404(self.get_queryset(), pk=pk)
        return Response(
            {
                "conversation": AgentConversationSerializer(conversation).data,
                "messages": AgentMessageSerializer(conversation.messages.order_by("created_at"), many=True).data,
            },
            status=status.HTTP_200_OK,
        )

    def destroy(self, request, slug, pk, project_id=None):
        if not self._has_scope_access():
            return self._scope_denied_response()

        conversation = get_object_or_404(self.get_queryset(), pk=pk)
        conversation.delete(soft=False)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def chat(self, request, slug, conversation_id, project_id=None):
        if not self._has_scope_access():
            return self._scope_denied_response()

        serializer = AgentChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        conversation = get_object_or_404(self.get_chat_queryset(), pk=conversation_id)

        project_name = conversation.project.name if conversation.project_id else None
        project_identifier = conversation.project.identifier if conversation.project_id else None
        run_id = uuid4().hex
        request_id = (
            serializer.validated_data.get("client_request_id")
            or request.headers.get("X-Request-ID")
            or uuid4().hex
        )
        assistant_message_id = uuid4()

        context = AgentChatContext(
            workspace_slug=slug,
            workspace_id=str(conversation.workspace_id),
            user_id=str(request.user.id),
            request_id=request_id,
            run_id=run_id,
            project_name=project_name,
            project_id=str(conversation.project_id) if conversation.project_id else None,
            project_identifier=project_identifier,
        )

        def stream_chat():
            yield encode_sse_event(
                {
                    "type": "run.started",
                    "run_id": run_id,
                    "conversation_id": str(conversation.id),
                }
            )

            try:
                assistant_result = AgentChatService.generate_reply(
                    messages=self._build_chat_messages(conversation, serializer.validated_data["message"]),
                    context=context,
                )
            except AgentChatConfigurationError as exc:
                yield encode_sse_event(
                    {
                        "type": "run.failed",
                        "run_id": run_id,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "retryable": exc.retryable,
                        },
                    }
                )
                return
            except AgentChatError as exc:
                yield encode_sse_event(
                    {
                        "type": "run.failed",
                        "run_id": run_id,
                        "error": {
                            "code": exc.code,
                            "message": exc.message,
                            "retryable": exc.retryable,
                        },
                    }
                )
                return

            if isinstance(assistant_result, str):
                assistant_result = AgentChatResult(content=assistant_result)

            if assistant_result.content:
                yield encode_sse_event(
                    {
                        "type": "text.delta",
                        "run_id": run_id,
                        "message_id": str(assistant_message_id),
                        "delta": assistant_result.content,
                    }
                )

            for tool_call in assistant_result.tool_calls or []:
                yield encode_sse_event(
                    {
                        "type": "tool.call",
                        "run_id": run_id,
                        "message_id": str(assistant_message_id),
                        "call_id": tool_call["call_id"],
                        "tool_name": tool_call["tool_name"],
                        "input": tool_call["input"],
                    }
                )

            for tool_result in assistant_result.tool_results or []:
                yield encode_sse_event(
                    {
                        "type": "tool.result",
                        "run_id": run_id,
                        "message_id": str(assistant_message_id),
                        "call_id": tool_result["call_id"],
                        "tool_name": tool_result["tool_name"],
                        "success": tool_result["success"],
                        "output": tool_result["output"],
                        "error": tool_result["error"],
                    }
                )

            with transaction.atomic():
                user_message = AgentMessage(
                    conversation=conversation,
                    role=AgentMessage.Role.USER,
                    content=serializer.validated_data["message"],
                )
                user_message.save(created_by_id=request.user.id)

                assistant_message = AgentMessage(
                    id=assistant_message_id,
                    conversation=conversation,
                    role=AgentMessage.Role.ASSISTANT,
                    content=assistant_result.content,
                    tool_calls=assistant_result.tool_calls,
                    tool_results=assistant_result.tool_results,
                    status=assistant_result.status,
                )
                assistant_message.save(created_by_id=request.user.id)

                conversation.last_message_at = assistant_message.created_at
                conversation.save(update_fields=["last_message_at"], disable_auto_set_user=True)

            yield encode_sse_event(
                {
                    "type": "message.completed",
                    "run_id": run_id,
                    "message": AgentMessageSerializer(assistant_message).data,
                }
            )
            yield encode_sse_event(
                {
                    "type": "run.completed",
                    "run_id": run_id,
                }
            )

        response = StreamingHttpResponse(stream_chat(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        return response

    def _build_chat_messages(self, conversation, latest_user_message: str):
        messages = list(
            conversation.messages.order_by("created_at").values("role", "content")
        )
        messages.append({"role": AgentMessage.Role.USER, "content": latest_user_message})
        return messages
