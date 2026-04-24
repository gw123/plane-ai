/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { TriangleAlert } from "lucide-react";
import type { TAgentToolRenderModel } from "./tool-renderer-registry";

type ToolErrorCardProps = {
  result: Extract<TAgentToolRenderModel, { kind: "error" }>;
};

const formatToolName = (toolName: string) => toolName.split("_").join(" ");

export function ToolErrorCard(props: ToolErrorCardProps) {
  const {
    result: { error, toolName },
  } = props;

  return (
    <div className="shadow-sm w-full rounded-2xl border border-danger-subtle bg-danger-primary/5 p-4 text-primary">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-danger-primary/10 text-danger-primary">
          <TriangleAlert className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{formatToolName(toolName)} failed</div>
          <div className="text-xs mt-1 font-medium text-danger-primary">{error.code}</div>
          <div className="text-sm mt-2 leading-6 text-secondary">{error.message}</div>
        </div>
      </div>
    </div>
  );
}
