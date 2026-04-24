# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import os
import json
from dataclasses import dataclass
from typing import Any, List, Dict, Tuple

from openai import OpenAI

from plane.license.utils.instance_value import get_configuration_value
from plane.utils.exception_logger import log_exception


@dataclass(frozen=True)
class LLMProviderFailure:
    code: str
    message: str
    retryable: bool


@dataclass(frozen=True)
class LLMToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass(frozen=True)
class LLMChatCompletion:
    text: str
    tool_calls: list[LLMToolCall]


class LLMProvider:
    """Base class for LLM provider configurations."""

    name: str = ""
    models: List[str] = []
    default_model: str = ""
    supports_custom_models: bool = False

    @classmethod
    def get_config(cls) -> Dict[str, str | List[str]]:
        return {
            "name": cls.name,
            "models": cls.models,
            "default_model": cls.default_model,
        }


class OpenAIProvider(LLMProvider):
    name = "OpenAI"
    models = ["gpt-3.5-turbo", "gpt-4o-mini", "gpt-4o", "o1-mini", "o1-preview"]
    default_model = "gpt-4o-mini"
    supports_custom_models = True


class AnthropicProvider(LLMProvider):
    name = "Anthropic"
    models = [
        "claude-3-5-sonnet-20240620",
        "claude-3-haiku-20240307",
        "claude-3-opus-20240229",
        "claude-3-sonnet-20240229",
        "claude-2.1",
        "claude-2",
        "claude-instant-1.2",
        "claude-instant-1",
    ]
    default_model = "claude-3-sonnet-20240229"


class GeminiProvider(LLMProvider):
    name = "Gemini"
    models = ["gemini-pro", "gemini-1.5-pro-latest", "gemini-pro-vision"]
    default_model = "gemini-pro"


SUPPORTED_PROVIDERS = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
}


def get_llm_config() -> Tuple[str | None, str | None, str | None]:
    api_key, provider_key, model = get_configuration_value(
        [
            {
                "key": "LLM_API_KEY",
                "default": os.environ.get("LLM_API_KEY", None),
            },
            {
                "key": "LLM_PROVIDER",
                "default": os.environ.get("LLM_PROVIDER", "openai"),
            },
            {
                "key": "LLM_MODEL",
                "default": os.environ.get("LLM_MODEL", None),
            },
        ]
    )

    api_key = _clean_config_value(api_key)
    provider_key = _clean_config_value(provider_key)
    model = _clean_config_value(model)

    provider = SUPPORTED_PROVIDERS.get(provider_key.lower()) if provider_key else None
    if not provider:
        log_exception(ValueError(f"Unsupported provider: {provider_key}"))
        return None, None, None

    if not api_key:
        log_exception(ValueError(f"Missing API key for provider: {provider.name}"))
        return None, None, None

    if not model:
        model = provider.default_model

    if not provider.supports_custom_models and model not in provider.models:
        log_exception(
            ValueError(
                f"Model {model} not supported by {provider.name}. Supported models: {', '.join(provider.models)}"
            )
        )
        return None, None, None

    return api_key, model, provider_key


def _clean_config_value(value: Any) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip()
    return normalized or None


def get_llm_base_url() -> str | None:
    (base_url,) = get_configuration_value(
        [
            {
                "key": "LLM_BASE_URL",
                "default": (
                    os.environ.get("LLM_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                    or os.environ.get("OPENAI_API_BASE")
                ),
            }
        ]
    )
    return _clean_config_value(base_url)


def _normalize_model_name(model: str, provider: str) -> str:
    if provider.lower() == "gemini":
        return f"gemini/{model}"
    return model


def _get_openai_client(api_key: str) -> OpenAI:
    base_url = get_llm_base_url()
    if base_url:
        return OpenAI(api_key=api_key, base_url=base_url)
    return OpenAI(api_key=api_key)


def get_llm_response(task, prompt, api_key: str, model: str, provider: str) -> Tuple[str | None, str | None]:
    final_text = task + "\n" + prompt
    try:
        client = _get_openai_client(api_key)
        chat_completion = client.chat.completions.create(
            model=_normalize_model_name(model, provider),
            messages=[{"role": "user", "content": final_text}],
        )
        text = chat_completion.choices[0].message.content
        return text, None
    except Exception as e:
        log_exception(e)
        error_type = e.__class__.__name__
        if error_type == "AuthenticationError":
            return None, f"Invalid API key for {provider}"
        elif error_type == "RateLimitError":
            return None, f"Rate limit exceeded for {provider}"
        else:
            return None, f"Error occurred while generating response from {provider}"


def _map_chat_completion_error(exception: Exception) -> LLMProviderFailure:
    error_type = exception.__class__.__name__

    if error_type == "AuthenticationError":
        return LLMProviderFailure(
            code="AGENT_PROVIDER_ERROR",
            message="Agent provider authentication failed.",
            retryable=False,
        )

    if error_type == "RateLimitError":
        return LLMProviderFailure(
            code="AGENT_PROVIDER_ERROR",
            message="Agent provider rate limit exceeded.",
            retryable=True,
        )

    if error_type in {"APITimeoutError", "TimeoutError"}:
        return LLMProviderFailure(
            code="AGENT_PROVIDER_TIMEOUT",
            message="Agent provider request timed out.",
            retryable=True,
        )

    return LLMProviderFailure(
        code="AGENT_PROVIDER_ERROR",
        message="Agent provider failed to generate a response.",
        retryable=True,
    )


def get_chat_completion(
    messages: list[dict[str, Any]],
    api_key: str,
    model: str,
    provider: str,
    system_prompt: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> Tuple[LLMChatCompletion | None, LLMProviderFailure | None]:
    try:
        chat_messages = []
        if system_prompt:
            chat_messages.append({"role": "system", "content": system_prompt})
        chat_messages.extend(messages)

        client = _get_openai_client(api_key)
        request_kwargs = {
            "model": _normalize_model_name(model, provider),
            "messages": chat_messages,
        }
        if tools:
            request_kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["input_schema"],
                    },
                }
                for tool in tools
            ]

        chat_completion = client.chat.completions.create(
            **request_kwargs,
        )
        message = chat_completion.choices[0].message
        text = message.content if isinstance(message.content, str) else ""
        tool_calls = []
        for tool_call in message.tool_calls or []:
            try:
                arguments = tool_call.function.arguments or "{}"
                input_data = json.loads(arguments)
                if not isinstance(input_data, dict):
                    raise ValueError("Tool arguments must decode to an object.")
            except Exception:
                return (
                    None,
                    LLMProviderFailure(
                        code="AGENT_PROVIDER_ERROR",
                        message="Agent provider returned invalid tool input.",
                        retryable=True,
                    ),
                )

            tool_calls.append(
                LLMToolCall(
                    id=tool_call.id,
                    name=tool_call.function.name,
                    input=input_data,
                )
            )

        if tool_calls or (isinstance(text, str) and text.strip()):
            return LLMChatCompletion(text=text.strip(), tool_calls=tool_calls), None

        return (
            None,
            LLMProviderFailure(
                code="AGENT_PROVIDER_ERROR",
                message="Agent provider returned an empty response.",
                retryable=True,
            ),
        )
    except Exception as e:
        log_exception(e)
        return None, _map_chat_completion_error(e)
