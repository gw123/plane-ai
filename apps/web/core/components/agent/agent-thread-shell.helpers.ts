/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { AgentService, IAgentScopeRoute } from "@plane/services";
import type { IAgentConversationDetailResponse } from "@plane/types";

type CleanupCreatedConversationAfterFailureParams = {
  agentService: Pick<AgentService, "deleteConversation" | "getConversation">;
  scope: IAgentScopeRoute;
  conversationId: string;
  revalidateConversations: () => Promise<unknown>;
  removeConversation: (conversationId: string) => Promise<unknown>;
};

type CleanupCreatedConversationAfterFailureResult = {
  deleted: boolean;
  detail: IAgentConversationDetailResponse | null;
};

export const cleanupCreatedConversationAfterFailure = async ({
  agentService,
  scope,
  conversationId,
  revalidateConversations,
  removeConversation,
}: CleanupCreatedConversationAfterFailureParams): Promise<CleanupCreatedConversationAfterFailureResult> => {
  const detail = await agentService.getConversation(scope, conversationId).catch(() => null);

  // Never delete a thread unless we can prove it is still empty after the failed stream.
  if (!detail || detail.messages.length > 0) {
    await revalidateConversations();
    return { deleted: false, detail };
  }

  try {
    await agentService.deleteConversation(scope, conversationId);
    await removeConversation(conversationId);
    return { deleted: true, detail };
  } catch {
    await revalidateConversations();
    return { deleted: false, detail };
  }
};
