/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { cleanupCreatedConversationAfterFailure } from "./agent-thread-shell.helpers.ts";

const scope = { workspaceSlug: "plane" };

test("cleanupCreatedConversationAfterFailure deletes a created thread only when it is confirmed empty", async () => {
  let deletedConversationId = null;
  let removedConversationId = null;
  let revalidated = false;

  const result = await cleanupCreatedConversationAfterFailure({
    agentService: {
      getConversation: async () => ({
        conversation: {
          id: "conv-empty",
          workspace_id: "ws-1",
          project_id: null,
          scope: "workspace",
          title: "New conversation",
          status: "active",
          created_by_id: "user-1",
          last_message_at: null,
          created_at: "2026-04-24T00:00:00Z",
          updated_at: "2026-04-24T00:00:00Z",
        },
        messages: [],
      }),
      deleteConversation: async (_scope, conversationId) => {
        deletedConversationId = conversationId;
      },
    },
    scope,
    conversationId: "conv-empty",
    removeConversation: async (conversationId) => {
      removedConversationId = conversationId;
    },
    revalidateConversations: async () => {
      revalidated = true;
    },
  });

  assert.equal(result.deleted, true);
  assert.equal(deletedConversationId, "conv-empty");
  assert.equal(removedConversationId, "conv-empty");
  assert.equal(revalidated, false);
});

test("cleanupCreatedConversationAfterFailure keeps a created thread when messages were already persisted", async () => {
  let deleteCalled = false;
  let removedConversationId = null;
  let revalidateCalls = 0;

  const result = await cleanupCreatedConversationAfterFailure({
    agentService: {
      getConversation: async () => ({
        conversation: {
          id: "conv-persisted",
          workspace_id: "ws-1",
          project_id: null,
          scope: "workspace",
          title: "Recovered conversation",
          status: "active",
          created_by_id: "user-1",
          last_message_at: "2026-04-24T00:01:00Z",
          created_at: "2026-04-24T00:00:00Z",
          updated_at: "2026-04-24T00:01:00Z",
        },
        messages: [
          {
            id: "msg-1",
            conversation_id: "conv-persisted",
            role: "user",
            content: "hello",
            tool_calls: null,
            tool_results: null,
            status: "completed",
            created_at: "2026-04-24T00:00:00Z",
          },
        ],
      }),
      deleteConversation: async () => {
        deleteCalled = true;
      },
    },
    scope,
    conversationId: "conv-persisted",
    removeConversation: async (conversationId) => {
      removedConversationId = conversationId;
    },
    revalidateConversations: async () => {
      revalidateCalls += 1;
    },
  });

  assert.equal(result.deleted, false);
  assert.equal(deleteCalled, false);
  assert.equal(removedConversationId, null);
  assert.equal(revalidateCalls, 1);
});
