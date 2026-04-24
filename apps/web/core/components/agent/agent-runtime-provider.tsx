/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { ReactNode } from "react";
import {
  AssistantRuntimeProvider,
  type AppendMessage,
  type ThreadMessageLike,
  useExternalStoreRuntime,
} from "@assistant-ui/react";

type AgentRuntimeProviderProps = {
  messages: ThreadMessageLike[];
  isDisabled?: boolean;
  isLoading?: boolean;
  isRunning: boolean;
  onNew: (message: AppendMessage) => Promise<void>;
  children: ReactNode;
};

export function AgentRuntimeProvider(props: AgentRuntimeProviderProps) {
  const { messages, isDisabled = false, isLoading = false, isRunning, onNew, children } = props;

  const runtime = useExternalStoreRuntime<ThreadMessageLike>({
    messages,
    isDisabled,
    isLoading,
    isRunning,
    convertMessage: (message) => message,
    onNew,
  });

  return <AssistantRuntimeProvider runtime={runtime}>{children}</AssistantRuntimeProvider>;
}
