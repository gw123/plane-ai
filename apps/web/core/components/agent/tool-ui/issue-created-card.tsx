/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { CheckCircle2 } from "lucide-react";
import { PriorityIcon, StateGroupIcon } from "@plane/propel/icons";
import { cn } from "@plane/utils";
import type { TAgentToolRenderModel } from "./tool-renderer-registry";

type IssueCreatedCardProps = {
  result: Extract<TAgentToolRenderModel, { kind: "create_issue" }>;
};

const formatPriorityLabel = (priority: string) => {
  if (priority === "none") return "No priority";
  return `${priority.charAt(0).toUpperCase()}${priority.slice(1)} priority`;
};

export function IssueCreatedCard(props: IssueCreatedCardProps) {
  const {
    result: { output },
  } = props;

  return (
    <div className="border-positive-border bg-positive-primary/5 shadow-sm w-full rounded-2xl border p-4 text-primary">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-positive-primary text-11 font-medium tracking-[0.12em] uppercase">Issue created</div>
          <div className="mt-2 flex items-center gap-2">
            <PriorityIcon priority={output.priority} withContainer size={12} />
            <span className="text-sm font-semibold">{output.display_id}</span>
          </div>
        </div>
        <div className="bg-positive-primary/10 text-positive-primary flex items-center gap-1 rounded-full px-2.5 py-1 text-11 font-medium">
          <CheckCircle2 className="h-3.5 w-3.5" />
          <span>Saved</span>
        </div>
      </div>

      <div className="text-sm mt-3 leading-6 font-medium">{output.name}</div>

      <div className="text-xs mt-3 flex flex-wrap items-center gap-2 text-secondary">
        <div className="flex items-center gap-1 rounded-full border border-subtle bg-surface-1 px-2.5 py-1">
          <StateGroupIcon stateGroup={output.state.group} color={output.state.color} className="size-3 shrink-0" />
          <span className="font-medium text-primary">{output.state.name}</span>
        </div>
        <div
          className={cn(
            "rounded-full border border-subtle bg-surface-1 px-2.5 py-1 font-medium text-primary",
            output.priority === "urgent" && "border-priority-urgent/40 text-priority-urgent",
            output.priority === "high" && "border-priority-high/40 text-priority-high",
            output.priority === "medium" && "border-priority-medium/40 text-priority-medium",
            output.priority === "low" && "border-priority-low/40 text-priority-low"
          )}
        >
          {formatPriorityLabel(output.priority)}
        </div>
      </div>
    </div>
  );
}
