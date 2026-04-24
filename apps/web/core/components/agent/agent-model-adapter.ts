/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AppendMessage, MessageStatus, ThreadMessageLike } from "@assistant-ui/react";
import type { IAgentMessage, IAgentToolCall, IAgentToolResult, TAgentMessageStatus } from "@plane/types";

type IAgentThreadCustomMetadata = {
  agentConversationId?: string;
  agentToolCalls?: IAgentToolCall[] | null;
  agentToolResults?: IAgentToolResult[] | null;
  agentOptimistic?: boolean;
  agentPlaceholder?: boolean;
};

const COMPLETE_STATUS: MessageStatus = {
  type: "complete",
  reason: "stop",
};

const FAILED_STATUS = (message: string): MessageStatus => ({
  type: "incomplete",
  reason: "error",
  error: { message },
});

const RUNNING_STATUS: MessageStatus = {
  type: "running",
};

const mapAssistantStatus = (status: TAgentMessageStatus, fallbackMessage: string): MessageStatus => {
  if (status === "completed") return COMPLETE_STATUS;
  return FAILED_STATUS(fallbackMessage);
};

export const collectAppendMessageText = (message: AppendMessage): string => {
  return message.content
    .flatMap((part) => (part.type === "text" ? [part.text] : []))
    .join("")
    .trim();
};

export const toThreadMessageLike = (message: IAgentMessage): ThreadMessageLike => {
  const createdAt = new Date(message.created_at);

  return {
    role: message.role,
    id: message.id,
    content: message.content,
    createdAt,
    status:
      message.role === "assistant"
        ? mapAssistantStatus(message.status, message.content || "Agent run failed")
        : undefined,
    metadata: {
      custom: {
        agentConversationId: message.conversation_id,
        agentToolCalls: message.tool_calls,
        agentToolResults: message.tool_results,
      },
    },
  };
};

const getAgentThreadCustomMetadata = (message: ThreadMessageLike): IAgentThreadCustomMetadata | undefined =>
  message.metadata?.custom as IAgentThreadCustomMetadata | undefined;

export const getAgentMessageToolResults = (message: ThreadMessageLike): IAgentToolResult[] | null =>
  getAgentThreadCustomMetadata(message)?.agentToolResults ?? null;

export const createOptimisticUserMessage = (id: string, content: string): ThreadMessageLike => ({
  role: "user",
  id,
  content,
  createdAt: new Date(),
  metadata: {
    custom: {
      agentOptimistic: true,
    },
  },
});

export const createOptimisticAssistantMessage = (id: string): ThreadMessageLike => ({
  role: "assistant",
  id,
  content: "Working...",
  createdAt: new Date(),
  status: RUNNING_STATUS,
  metadata: {
    custom: {
      agentOptimistic: true,
      agentPlaceholder: true,
    },
  },
});

export const updateAssistantMessageDelta = (
  message: ThreadMessageLike,
  delta: string,
  nextId?: string
): ThreadMessageLike => {
  const currentContent = typeof message.content === "string" ? message.content : "";
  const placeholder = getAgentThreadCustomMetadata(message);

  return {
    ...message,
    id: nextId ?? message.id,
    content: placeholder?.agentPlaceholder ? delta : `${currentContent}${delta}`,
    status: RUNNING_STATUS,
    metadata: {
      ...message.metadata,
      custom: {
        ...(getAgentThreadCustomMetadata(message) as Record<string, unknown> | undefined),
        agentPlaceholder: false,
      },
    },
  };
};

export const finalizeAssistantMessage = (
  message: ThreadMessageLike,
  completedMessage: IAgentMessage
): ThreadMessageLike => toThreadMessageLike(completedMessage);

export const replaceMessageById = (
  messages: ThreadMessageLike[],
  targetIds: string[],
  replacement: ThreadMessageLike
): ThreadMessageLike[] => {
  const matchIdSet = new Set(targetIds);
  const nextMessages = messages.map((item) => (matchIdSet.has(item.id ?? "") ? replacement : item));

  if (!nextMessages.some((item) => item.id === replacement.id)) {
    return [...nextMessages, replacement];
  }

  return nextMessages;
};
