/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { API_BASE_URL } from "@plane/constants";
import type {
  IAgentChatPayload,
  IAgentConversation,
  IAgentConversationDetailResponse,
  IAgentConversationListResponse,
  IAgentCreateConversationPayload,
  TAgentStreamEvent,
} from "@plane/types";
import { APIService } from "../api.service";

export interface IAgentScopeRoute {
  workspaceSlug: string;
  projectId?: string | null;
}

export interface IAgentStreamChatOptions {
  onEvent?: (event: TAgentStreamEvent) => void;
  signal?: AbortSignal;
}

export class AgentServiceError extends Error {
  status?: number;
  details?: unknown;

  constructor(message: string, options?: { status?: number; details?: unknown }) {
    super(message);
    this.name = "AgentServiceError";
    this.status = options?.status;
    this.details = options?.details;
  }
}

const getScopeBasePath = ({ workspaceSlug, projectId }: IAgentScopeRoute): string => {
  if (projectId) {
    return `/api/workspaces/${workspaceSlug}/projects/${projectId}/agent/conversations/`;
  }

  return `/api/workspaces/${workspaceSlug}/agent/conversations/`;
};

const extractErrorMessage = (payload: unknown, fallback: string): string => {
  if (!payload || typeof payload !== "object") return fallback;

  if ("error" in payload) {
    const error = (payload as { error?: unknown }).error;

    if (typeof error === "string") return error;
    if (
      error &&
      typeof error === "object" &&
      "message" in error &&
      typeof (error as { message?: unknown }).message === "string"
    ) {
      return (error as { message: string }).message;
    }
  }

  if ("message" in payload && typeof payload.message === "string") {
    return payload.message;
  }

  const firstEntry = Object.values(payload as Record<string, unknown>)[0];
  if (Array.isArray(firstEntry) && typeof firstEntry[0] === "string") {
    return firstEntry[0];
  }

  return fallback;
};

const parseSSEPayload = (rawEvent: string): TAgentStreamEvent[] => {
  const data = rawEvent
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trim())
    .join("");

  if (!data) return [];

  return [JSON.parse(data) as TAgentStreamEvent];
};

const flushSSEBuffer = (buffer: string): { events: TAgentStreamEvent[]; remaining: string } => {
  const chunks = buffer.split("\n\n");
  const remaining = chunks.pop() ?? "";
  const events = chunks.flatMap((chunk) => parseSSEPayload(chunk));

  return { events, remaining };
};

export class AgentService extends APIService {
  constructor(BASE_URL?: string) {
    super(BASE_URL || API_BASE_URL);
  }

  async listConversations(scope: IAgentScopeRoute): Promise<IAgentConversationListResponse> {
    return this.get(getScopeBasePath(scope))
      .then((response) => response?.data as IAgentConversationListResponse)
      .catch((error) => {
        throw new AgentServiceError(extractErrorMessage(error?.response?.data, "Failed to load conversations."), {
          details: error?.response?.data,
          status: error?.response?.status,
        });
      });
  }

  async createConversation(
    scope: IAgentScopeRoute,
    payload: IAgentCreateConversationPayload = {}
  ): Promise<IAgentConversation> {
    return this.post(getScopeBasePath(scope), payload)
      .then((response) => response?.data as IAgentConversation)
      .catch((error) => {
        throw new AgentServiceError(extractErrorMessage(error?.response?.data, "Failed to create conversation."), {
          details: error?.response?.data,
          status: error?.response?.status,
        });
      });
  }

  async getConversation(scope: IAgentScopeRoute, conversationId: string): Promise<IAgentConversationDetailResponse> {
    return this.get(`${getScopeBasePath(scope)}${conversationId}/`)
      .then((response) => response?.data as IAgentConversationDetailResponse)
      .catch((error) => {
        throw new AgentServiceError(extractErrorMessage(error?.response?.data, "Failed to load conversation."), {
          details: error?.response?.data,
          status: error?.response?.status,
        });
      });
  }

  async deleteConversation(scope: IAgentScopeRoute, conversationId: string): Promise<void> {
    return this.delete(`${getScopeBasePath(scope)}${conversationId}/`)
      .then(() => undefined)
      .catch((error) => {
        throw new AgentServiceError(extractErrorMessage(error?.response?.data, "Failed to delete conversation."), {
          details: error?.response?.data,
          status: error?.response?.status,
        });
      });
  }

  async streamConversationChat(
    scope: IAgentScopeRoute,
    conversationId: string,
    payload: IAgentChatPayload,
    options: IAgentStreamChatOptions = {}
  ): Promise<void> {
    const response = await fetch(`${this.baseURL}${getScopeBasePath(scope)}${conversationId}/chat/`, {
      method: "POST",
      body: JSON.stringify(payload),
      credentials: "include",
      headers: {
        Accept: "text/event-stream",
        "Content-Type": "application/json",
      },
      signal: options.signal,
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => null);

      throw new AgentServiceError(extractErrorMessage(errorPayload, "Failed to start agent run."), {
        details: errorPayload,
        status: response.status,
      });
    }

    if (!response.body) {
      throw new AgentServiceError("Agent response stream is unavailable.");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    const readNextChunk = async (): Promise<void> => {
      const { done, value } = await reader.read();
      if (value) {
        buffer += decoder.decode(value, { stream: !done });
      }

      const { events, remaining } = flushSSEBuffer(buffer);
      buffer = remaining;

      events.forEach((event) => options.onEvent?.(event));

      if (done) {
        const tail = flushSSEBuffer(`${buffer}\n\n`);
        tail.events.forEach((event) => options.onEvent?.(event));
        return;
      }

      await readNextChunk();
    };

    await readNextChunk();
  }
}
