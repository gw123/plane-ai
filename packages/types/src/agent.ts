/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

export type TAgentConversationScope = "workspace" | "project";
export type TAgentConversationStatus = "active" | "archived";
export type TAgentMessageRole = "user" | "assistant";
export type TAgentMessageStatus = "completed" | "failed";
export type TAgentToolCallStatus = "pending" | "running" | "completed" | "failed";

export interface IAgentToolError {
  code: string;
  message: string;
}

export interface IAgentToolCall {
  call_id: string;
  tool_name: string;
  input: Record<string, unknown>;
  status: TAgentToolCallStatus;
}

export interface IAgentToolResult {
  call_id: string;
  tool_name: string;
  success: boolean;
  output: Record<string, unknown> | null;
  error: IAgentToolError | null;
}

export interface IAgentConversation {
  id: string;
  workspace_id: string;
  project_id: string | null;
  scope: TAgentConversationScope;
  title: string;
  status: TAgentConversationStatus;
  created_by_id: string | null;
  last_message_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IAgentMessage {
  id: string;
  conversation_id: string;
  role: TAgentMessageRole;
  content: string;
  tool_calls: IAgentToolCall[] | null;
  tool_results: IAgentToolResult[] | null;
  status: TAgentMessageStatus;
  created_at: string;
}

export interface IAgentConversationListResponse {
  results: IAgentConversation[];
}

export interface IAgentConversationDetailResponse {
  conversation: IAgentConversation;
  messages: IAgentMessage[];
}

export interface IAgentCreateConversationPayload {
  title?: string;
}

export interface IAgentChatPayload {
  message: string;
  client_request_id?: string;
}

export interface IAgentRunError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface IAgentRunStartedEvent {
  type: "run.started";
  run_id: string;
  conversation_id: string;
}

export interface IAgentTextDeltaEvent {
  type: "text.delta";
  run_id: string;
  message_id: string;
  delta: string;
}

export interface IAgentToolCallEvent {
  type: "tool.call";
  run_id: string;
  message_id: string;
  call_id: string;
  tool_name: string;
  input: Record<string, unknown>;
}

export interface IAgentToolResultEvent {
  type: "tool.result";
  run_id: string;
  message_id: string;
  call_id: string;
  tool_name: string;
  success: boolean;
  output: unknown;
  error: unknown;
}

export interface IAgentMessageCompletedEvent {
  type: "message.completed";
  run_id: string;
  message: IAgentMessage;
}

export interface IAgentRunCompletedEvent {
  type: "run.completed";
  run_id: string;
}

export interface IAgentRunFailedEvent {
  type: "run.failed";
  run_id: string;
  error: IAgentRunError;
}

export type TAgentStreamEvent =
  | IAgentRunStartedEvent
  | IAgentTextDeltaEvent
  | IAgentToolCallEvent
  | IAgentToolResultEvent
  | IAgentMessageCompletedEvent
  | IAgentRunCompletedEvent
  | IAgentRunFailedEvent;
