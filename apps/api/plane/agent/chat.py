# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json
from dataclasses import dataclass

from plane.agent.tools import AgentToolExecutionContext, AgentToolRegistry
from plane.db.models import AgentMessage
from plane.llm.provider import LLMProviderFailure, LLMToolCall, get_chat_completion, get_llm_config


AGENT_PROVIDER_ERROR_CODE = "AGENT_PROVIDER_ERROR"
AGENT_PROVIDER_TIMEOUT_CODE = "AGENT_PROVIDER_TIMEOUT"


class AgentChatError(Exception):
    """Base exception for normalized agent chat failures."""

    def __init__(self, message: str, *, code: str, retryable: bool, status_code: int):
        super().__init__(message)
        self.message = message
        self.code = code
        self.retryable = retryable
        self.status_code = status_code

    def to_response_data(self) -> dict[str, dict[str, str | bool]]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "retryable": self.retryable,
            }
        }


class AgentChatConfigurationError(AgentChatError):
    """Raised when the chat provider is not configured."""

    def __init__(self, message: str = "LLM provider API key and model are required"):
        super().__init__(
            message,
            code=AGENT_PROVIDER_ERROR_CODE,
            retryable=False,
            status_code=400,
        )


class AgentChatProviderError(AgentChatError):
    """Raised when the chat provider fails to produce a response."""

    def __init__(
        self,
        message: str = "Agent provider failed to generate a response.",
        *,
        retryable: bool = True,
    ):
        super().__init__(
            message,
            code=AGENT_PROVIDER_ERROR_CODE,
            retryable=retryable,
            status_code=502,
        )


class AgentChatProviderTimeoutError(AgentChatError):
    """Raised when the chat provider request times out."""

    def __init__(self, message: str = "Agent provider request timed out."):
        super().__init__(
            message,
            code=AGENT_PROVIDER_TIMEOUT_CODE,
            retryable=True,
            status_code=504,
        )


@dataclass(frozen=True)
class AgentChatContext:
    workspace_slug: str
    workspace_id: str
    user_id: str
    request_id: str
    run_id: str
    project_name: str | None = None
    project_id: str | None = None
    project_identifier: str | None = None


@dataclass(frozen=True)
class AgentChatResult:
    content: str
    tool_calls: list[dict] | None = None
    tool_results: list[dict] | None = None
    status: str = AgentMessage.Status.COMPLETED


class AgentChatService:
    @classmethod
    def build_system_prompt(cls, context: AgentChatContext) -> str:
        prompt_lines = [
            "You are Plane Agent.",
            "Answer clearly, briefly, and truthfully.",
            "Use tools when they are available and required to answer accurately.",
            "Do not claim that you created, updated, or fetched records unless the tool result confirms it.",
            f"Current workspace slug: {context.workspace_slug}.",
        ]

        if context.project_name and context.project_identifier:
            prompt_lines.append(
                f"Current project: {context.project_name} ({context.project_identifier})."
            )

        return "\n".join(prompt_lines)

    @classmethod
    def generate_reply(cls, messages: list[dict[str, str]], context: AgentChatContext) -> AgentChatResult:
        api_key, model, provider = get_llm_config()
        if not api_key or not model or not provider:
            raise AgentChatConfigurationError("LLM provider API key and model are required")

        tools = AgentToolRegistry.list(scope="project" if context.project_id else "workspace")
        completion, error = get_chat_completion(
            messages=messages,
            api_key=api_key,
            model=model,
            provider=provider,
            system_prompt=cls.build_system_prompt(context),
            tools=[tool.to_provider_tool() for tool in tools] or None,
        )

        if error:
            cls._raise_provider_error(error)

        if completion is None:
            raise AgentChatProviderError("Agent provider returned an empty response.")

        if not completion.tool_calls:
            return AgentChatResult(content=completion.text.strip())

        execution_context = AgentToolExecutionContext(
            request_id=context.request_id,
            run_id=context.run_id,
            workspace_id=context.workspace_id,
            project_id=context.project_id,
            user_id=context.user_id,
        )
        tool_calls, tool_results = cls._execute_tool_calls(completion.tool_calls, execution_context)
        follow_up_completion, follow_up_error = get_chat_completion(
            messages=cls._build_follow_up_messages(messages, completion.tool_calls, tool_results),
            api_key=api_key,
            model=model,
            provider=provider,
            system_prompt=cls.build_system_prompt(context),
        )

        if follow_up_error:
            cls._raise_provider_error(follow_up_error)

        if follow_up_completion is None or not follow_up_completion.text:
            raise AgentChatProviderError("Agent provider returned an empty response.")

        status = (
            AgentMessage.Status.FAILED
            if any(tool_result["success"] is False for tool_result in tool_results)
            else AgentMessage.Status.COMPLETED
        )

        return AgentChatResult(
            content=follow_up_completion.text.strip(),
            tool_calls=tool_calls,
            tool_results=tool_results,
            status=status,
        )

    @staticmethod
    def _execute_tool_calls(
        tool_calls: list[LLMToolCall],
        context: AgentToolExecutionContext,
    ) -> tuple[list[dict], list[dict]]:
        normalized_calls = []
        normalized_results = []

        for tool_call in tool_calls:
            result = AgentToolRegistry.execute(tool_call.name, tool_call.input, context)
            normalized_calls.append(
                {
                    "call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "input": tool_call.input,
                    "status": "completed" if result.success else "failed",
                }
            )
            normalized_results.append(
                {
                    "call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }
            )

        return normalized_calls, normalized_results

    @staticmethod
    def _build_follow_up_messages(
        messages: list[dict[str, str]],
        tool_calls: list[LLMToolCall],
        tool_results: list[dict],
    ) -> list[dict]:
        assistant_message = {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.name,
                        "arguments": json.dumps(tool_call.input),
                    },
                }
                for tool_call in tool_calls
            ],
        }
        tool_messages = [
            {
                "role": "tool",
                "tool_call_id": tool_result["call_id"],
                "content": json.dumps(
                    {
                        "success": tool_result["success"],
                        "output": tool_result["output"],
                        "error": tool_result["error"],
                    }
                ),
            }
            for tool_result in tool_results
        ]
        return [*messages, assistant_message, *tool_messages]

    @staticmethod
    def _raise_provider_error(error: LLMProviderFailure) -> None:
        if error.code == AGENT_PROVIDER_TIMEOUT_CODE:
            raise AgentChatProviderTimeoutError(error.message)

        raise AgentChatProviderError(error.message, retryable=error.retryable)
