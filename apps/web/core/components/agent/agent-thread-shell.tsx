/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { observer } from "mobx-react";
import { useNavigate } from "react-router";
import useSWR from "swr";
import { Bot, ChevronRight, Clock3, Loader2, MessageSquareMore, Plus } from "lucide-react";
import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
  type ThreadMessageLike,
  type AppendMessage,
} from "@assistant-ui/react";
import { Button, Spinner } from "@plane/ui";
import { calculateTimeAgo, cn } from "@plane/utils";
import { AgentService, type IAgentScopeRoute } from "@plane/services";
import type { IAgentConversation, IAgentConversationListResponse } from "@plane/types";
import { AgentRuntimeProvider } from "./agent-runtime-provider";
import {
  collectAppendMessageText,
  createOptimisticAssistantMessage,
  createOptimisticUserMessage,
  finalizeAssistantMessage,
  replaceMessageById,
  toThreadMessageLike,
  updateAssistantMessageDelta,
} from "./agent-model-adapter";
import { cleanupCreatedConversationAfterFailure } from "./agent-thread-shell.helpers";

type AgentThreadShellProps = IAgentScopeRoute & {
  conversationId?: string;
  title: string;
  subtitle: string;
};

const agentService = new AgentService();

const buildAgentPath = (scope: IAgentScopeRoute, conversationId?: string) => {
  if (scope.projectId) {
    return conversationId
      ? `/${scope.workspaceSlug}/projects/${scope.projectId}/agent/${conversationId}`
      : `/${scope.workspaceSlug}/projects/${scope.projectId}/agent`;
  }

  return conversationId ? `/${scope.workspaceSlug}/agent/${conversationId}` : `/${scope.workspaceSlug}/agent`;
};

const getConversationLabel = (conversation: IAgentConversation) => {
  if (conversation.last_message_at) {
    return calculateTimeAgo(conversation.last_message_at);
  }

  return calculateTimeAgo(conversation.created_at);
};

const getMessageText = (message: ThreadMessageLike) => (typeof message.content === "string" ? message.content : "");

export const AgentThreadShell = observer(function AgentThreadShell(props: AgentThreadShellProps) {
  const { workspaceSlug, projectId, conversationId, title, subtitle } = props;
  const scope = useMemo<IAgentScopeRoute>(() => ({ workspaceSlug, projectId }), [workspaceSlug, projectId]);
  const navigate = useNavigate();
  const isMountedRef = useRef(true);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [messages, setMessages] = useState<ThreadMessageLike[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isCreatingConversation, setIsCreatingConversation] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const conversationsKey = projectId
    ? `agent-conversations:${workspaceSlug}:${projectId}`
    : `agent-conversations:${workspaceSlug}`;
  const conversationKey = conversationId
    ? `agent-conversation:${workspaceSlug}:${projectId ?? "workspace"}:${conversationId}`
    : null;

  const {
    data: conversationsResponse = { results: [] },
    error: conversationsError,
    isLoading: isConversationsLoading,
    mutate: mutateConversations,
  } = useSWR(conversationsKey, () => agentService.listConversations(scope));
  const conversations = conversationsResponse.results;

  const {
    data: conversationDetail,
    error: conversationError,
    isLoading: isConversationLoading,
    mutate: mutateConversation,
  } = useSWR(conversationKey, () => agentService.getConversation(scope, conversationId ?? ""), {
    revalidateOnFocus: false,
  });

  useEffect(() => {
    if (!conversationId) {
      setMessages([]);
      setStreamError(null);
      return;
    }

    if (conversationDetail?.conversation.id === conversationId) {
      setMessages(conversationDetail.messages.map(toThreadMessageLike));
      setStreamError(null);
    }
  }, [conversationDetail, conversationId]);

  useEffect(
    () => () => {
      isMountedRef.current = false;
      abortControllerRef.current?.abort();
    },
    []
  );

  const syncConversationDetail = useCallback(
    async (targetConversationId: string) => {
      const detail = await agentService.getConversation(scope, targetConversationId);
      const threadMessages = detail.messages.map(toThreadMessageLike);

      if (isMountedRef.current) {
        setMessages(threadMessages);
      }

      if (conversationId === targetConversationId) {
        await mutateConversation(detail, { revalidate: false });
      }

      await mutateConversations();
      return detail;
    },
    [conversationId, mutateConversation, mutateConversations, scope]
  );

  const removeConversationFromList = useCallback(
    async (targetConversationId: string) => {
      await mutateConversations(
        (current: IAgentConversationListResponse | undefined) => ({
          results: current?.results.filter((item) => item.id !== targetConversationId) ?? [],
        }),
        {
          revalidate: false,
        }
      );
    },
    [mutateConversations]
  );

  const revalidateConversationList = useCallback(async () => {
    await mutateConversations();
  }, [mutateConversations]);

  const handleNewMessage = useCallback(
    async (message: AppendMessage) => {
      const text = collectAppendMessageText(message);
      if (!text) return;

      const snapshot = messages;
      const clientRequestId = crypto.randomUUID();
      const userMessageId = `agent-user-${clientRequestId}`;
      const assistantMessageId = `agent-assistant-${clientRequestId}`;
      let activeConversationId = conversationId;
      let createdConversation: IAgentConversation | null = null;
      let runFailed = false;
      let streamFailureMessage: string | null = null;

      abortControllerRef.current?.abort();
      const abortController = new AbortController();
      abortControllerRef.current = abortController;

      setStreamError(null);
      setIsRunning(true);
      setMessages([
        ...snapshot,
        createOptimisticUserMessage(userMessageId, text),
        createOptimisticAssistantMessage(assistantMessageId),
      ]);

      try {
        if (!activeConversationId) {
          setIsCreatingConversation(true);
          const nextConversation = await agentService.createConversation(scope);
          createdConversation = nextConversation;
          activeConversationId = nextConversation.id;
          await mutateConversations(
            (current: IAgentConversationListResponse | undefined) => ({
              results: [nextConversation, ...(current?.results ?? [])],
            }),
            {
              revalidate: false,
            }
          );
        }

        await agentService.streamConversationChat(
          scope,
          activeConversationId,
          {
            client_request_id: clientRequestId,
            message: text,
          },
          {
            signal: abortController.signal,
            onEvent: (event) => {
              if (event.type === "run.failed") {
                runFailed = true;
                streamFailureMessage = event.error.message;
                setStreamError(event.error.message);
                return;
              }

              if (event.type === "text.delta") {
                setMessages((current) =>
                  replaceMessageById(
                    current,
                    [assistantMessageId, event.message_id],
                    updateAssistantMessageDelta(
                      current.find((item) => item.id === event.message_id || item.id === assistantMessageId) ??
                        createOptimisticAssistantMessage(event.message_id),
                      event.delta,
                      event.message_id
                    )
                  )
                );
                return;
              }

              if (event.type === "message.completed") {
                setMessages((current) =>
                  replaceMessageById(
                    current,
                    [assistantMessageId, event.message.id],
                    finalizeAssistantMessage(
                      current.find((item) => item.id === assistantMessageId || item.id === event.message.id) ??
                        createOptimisticAssistantMessage(event.message.id),
                      event.message
                    )
                  )
                );
              }
            },
          }
        );

        if (runFailed) {
          throw new Error("Agent run failed.");
        }

        await syncConversationDetail(activeConversationId);

        if (!conversationId && createdConversation) {
          navigate(buildAgentPath(scope, createdConversation.id), { replace: true });
        }
      } catch (error) {
        if (createdConversation) {
          await cleanupCreatedConversationAfterFailure({
            agentService,
            scope,
            conversationId: createdConversation.id,
            removeConversation: removeConversationFromList,
            revalidateConversations: revalidateConversationList,
          });
        }

        if (isMountedRef.current) {
          setMessages(snapshot);
          const messageText = error instanceof Error ? error.message : "Agent request failed.";
          setStreamError(streamFailureMessage ?? messageText);
        }
      } finally {
        if (isMountedRef.current) {
          setIsCreatingConversation(false);
          setIsRunning(false);
        }
      }
    },
    [
      conversationId,
      messages,
      mutateConversations,
      navigate,
      revalidateConversationList,
      removeConversationFromList,
      scope,
      syncConversationDetail,
    ]
  );

  const runtimeDisabled = Boolean(conversationId && conversationError) || isCreatingConversation;
  const activeConversationCandidate = conversationDetail?.conversation ?? null;
  const activeConversation = activeConversationCandidate?.id === conversationId ? activeConversationCandidate : null;
  const emptyState = !conversationId && messages.length === 0;
  const loadingCurrentConversation = Boolean(conversationId) && !activeConversation && isConversationLoading;

  return (
    <div className="flex h-full min-h-0 w-full flex-col overflow-hidden bg-surface-1">
      <div className="flex items-center justify-between gap-4 border-b border-subtle bg-surface-1 px-4 py-3">
        <div className="min-w-0">
          <div className="text-xs flex items-center gap-2 text-secondary">
            <Bot className="h-3.5 w-3.5" />
            <span>{subtitle}</span>
          </div>
          <h1 className="text-sm truncate font-medium text-primary">{title}</h1>
        </div>
        <Button
          variant="neutral-primary"
          size="sm"
          disabled={isRunning || isCreatingConversation}
          prependIcon={<Plus className="h-3.5 w-3.5" />}
          onClick={() => navigate(buildAgentPath(scope), { replace: false })}
        >
          New chat
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex max-h-72 w-full shrink-0 flex-col border-b border-subtle bg-surface-1 lg:h-full lg:max-h-none lg:w-80 lg:border-r lg:border-b-0">
          <div className="flex items-center justify-between border-b border-subtle px-4 py-3">
            <div>
              <p className="text-xs tracking-wide text-secondary uppercase">Conversations</p>
              <p className="text-11 text-tertiary">{conversations.length} threads</p>
            </div>
            {isConversationsLoading && <Spinner height="14px" width="14px" className="text-secondary" />}
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {conversationsError ? (
              <div className="text-sm flex h-full items-center justify-center px-4 py-8 text-center text-danger-primary">
                Failed to load conversations.
              </div>
            ) : conversations.length === 0 ? (
              <div className="text-sm flex h-full items-center justify-center px-4 py-8 text-center text-tertiary">
                No conversations yet.
              </div>
            ) : (
              <div className="space-y-1">
                {conversations.map((conversation) => {
                  const isActive = conversation.id === conversationId;

                  return (
                    <button
                      key={conversation.id}
                      type="button"
                      disabled={isRunning || isCreatingConversation}
                      onClick={() => navigate(buildAgentPath(scope, conversation.id))}
                      className={cn(
                        "flex w-full items-start gap-3 rounded-md border px-3 py-2 text-left transition-colors",
                        isActive
                          ? "border-accent-primary bg-accent-primary/10 text-primary"
                          : "border-transparent bg-transparent text-secondary hover:border-subtle hover:bg-surface-2 hover:text-primary",
                        (isRunning || isCreatingConversation) && "cursor-not-allowed opacity-70"
                      )}
                    >
                      <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-2 text-secondary">
                        <MessageSquareMore className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="text-sm truncate font-medium">{conversation.title}</div>
                        <div className="mt-0.5 flex items-center gap-1 text-11 text-tertiary">
                          <Clock3 className="h-3 w-3" />
                          <span>{getConversationLabel(conversation)}</span>
                        </div>
                      </div>
                      <ChevronRight className="mt-1 h-3.5 w-3.5 shrink-0 text-tertiary" />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </aside>

        <section className="flex min-h-0 flex-1 flex-col">
          {loadingCurrentConversation ? (
            <div className="flex h-full items-center justify-center">
              <Spinner />
            </div>
          ) : conversationError ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
              <div className="text-sm font-medium text-primary">Conversation unavailable</div>
              <div className="text-sm max-w-md text-tertiary">
                This thread cannot be loaded right now. Start a new chat or go back to the list.
              </div>
            </div>
          ) : emptyState ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-secondary">
                <Bot className="h-5 w-5" />
              </div>
              <div className="text-base font-medium text-primary">Start a thread</div>
              <div className="text-sm max-w-lg text-tertiary">
                Send a message to create a conversation and keep the history in Plane.
              </div>
            </div>
          ) : (
            <AgentRuntimeProvider
              messages={messages}
              isDisabled={runtimeDisabled}
              isLoading={isConversationLoading}
              isRunning={isRunning}
              onNew={handleNewMessage}
            >
              <ThreadPrimitive.Root className="flex min-h-0 flex-1 flex-col">
                <ThreadPrimitive.Viewport className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
                  <ThreadPrimitive.Messages>
                    {({ message }) => (
                      <MessagePrimitive.Root
                        key={message.id}
                        className={cn("mb-4 flex w-full", message.role === "user" ? "justify-end" : "justify-start")}
                      >
                        <div
                          className={cn(
                            "text-sm shadow-sm max-w-3xl rounded-2xl border px-4 py-3 leading-6",
                            message.role === "user"
                              ? "border-transparent bg-accent-primary text-on-color"
                              : "border-subtle bg-surface-2 text-primary"
                          )}
                        >
                          {message.role === "assistant" && message.status?.type === "running" ? (
                            <div className="flex items-center gap-2 text-tertiary">
                              <Loader2 className="h-4 w-4 animate-spin" />
                              <span>{getMessageText(message) || "Working..."}</span>
                            </div>
                          ) : (
                            <MessagePrimitive.Content />
                          )}
                        </div>
                      </MessagePrimitive.Root>
                    )}
                  </ThreadPrimitive.Messages>
                </ThreadPrimitive.Viewport>

                {streamError && (
                  <div className="text-sm mx-4 mb-3 rounded-md border border-danger-subtle bg-danger-primary/5 px-3 py-2 text-danger-primary">
                    {streamError}
                  </div>
                )}

                <div className="border-t border-subtle bg-surface-1 px-4 py-4">
                  <ComposerPrimitive.Root className="shadow-sm rounded-xl border border-subtle bg-surface-2 px-3 py-3">
                    <ComposerPrimitive.Input
                      className="text-sm min-h-28 w-full resize-none border-0 bg-transparent p-0 text-primary outline-none placeholder:text-tertiary focus:ring-0"
                      placeholder="Ask Plane Agent..."
                      submitMode="enter"
                    />
                    <div className="mt-3 flex items-center justify-between gap-3">
                      <div className="text-11 text-tertiary">Enter to send · Shift+Enter for newline</div>
                      <ComposerPrimitive.Send asChild>
                        <Button
                          variant="primary"
                          size="sm"
                          disabled={isRunning || isCreatingConversation}
                          prependIcon={<MessageSquareMore className="h-3.5 w-3.5" />}
                        >
                          Send
                        </Button>
                      </ComposerPrimitive.Send>
                    </div>
                  </ComposerPrimitive.Root>
                </div>
              </ThreadPrimitive.Root>
            </AgentRuntimeProvider>
          )}
        </section>
      </div>
    </div>
  );
});
