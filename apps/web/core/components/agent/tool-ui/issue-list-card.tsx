/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { ChevronRight, ListTodo } from "lucide-react";
import { useParams } from "react-router";
import { PriorityIcon, StateGroupIcon } from "@plane/propel/icons";
import { cn } from "@plane/utils";
import Link from "@/app/compat/next/link";
import type { TAgentToolRenderModel } from "./tool-renderer-registry";

type IssueListCardProps = {
  result: Extract<TAgentToolRenderModel, { kind: "list_issues" }>;
};

const formatPriorityLabel = (priority: string) => {
  if (priority === "none") return "No priority";
  return `${priority.charAt(0).toUpperCase()}${priority.slice(1)} priority`;
};

const formatTargetDate = (value: string | null) => {
  if (!value) return null;

  return value.slice(0, 10);
};

export function IssueListCard(props: IssueListCardProps) {
  const {
    result: { output },
  } = props;
  const { workspaceSlug } = useParams();
  const remainingIssues = Math.max(output.count - output.issues.length, 0);

  return (
    <div className="shadow-sm w-full rounded-2xl border border-subtle bg-surface-1 p-4 text-primary">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-11 font-medium tracking-[0.12em] text-secondary uppercase">Issues</div>
          <div className="text-sm mt-1 font-semibold">
            {output.count} matching issue{output.count === 1 ? "" : "s"}
          </div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 text-secondary">
          <ListTodo className="h-4 w-4" />
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {output.issues.length > 0 ? (
          output.issues.map((issue) => {
            const href = workspaceSlug ? `/${workspaceSlug}/browse/${issue.display_id}` : "#";
            const targetDate = formatTargetDate(issue.target_date);

            return (
              <Link
                key={issue.id}
                href={href}
                className="group hover:border-accent-primary/30 hover:bg-surface-3 flex items-center gap-3 rounded-xl border border-subtle bg-surface-2 px-3 py-3 transition-colors"
              >
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <div className="flex items-center gap-2">
                    <PriorityIcon priority={issue.priority} withContainer size={12} />
                    <span className="text-sm font-semibold">{issue.display_id}</span>
                  </div>
                  <div className="text-sm leading-6 font-medium text-primary">{issue.name}</div>
                  <div className="text-xs flex flex-wrap items-center gap-2 text-secondary">
                    <div className="flex items-center gap-1 rounded-full border border-subtle bg-surface-1 px-2.5 py-1">
                      <StateGroupIcon
                        stateGroup={issue.state.group}
                        color={issue.state.color}
                        className="size-3 shrink-0"
                      />
                      <span className="font-medium text-primary">{issue.state.name}</span>
                    </div>
                    <div
                      className={cn(
                        "rounded-full border border-subtle bg-surface-1 px-2.5 py-1 font-medium text-primary",
                        issue.priority === "urgent" && "border-priority-urgent/40 text-priority-urgent",
                        issue.priority === "high" && "border-priority-high/40 text-priority-high",
                        issue.priority === "medium" && "border-priority-medium/40 text-priority-medium",
                        issue.priority === "low" && "border-priority-low/40 text-priority-low"
                      )}
                    >
                      {formatPriorityLabel(issue.priority)}
                    </div>
                    {targetDate && (
                      <div className="rounded-full border border-subtle bg-surface-1 px-2.5 py-1 font-medium text-primary">
                        Due {targetDate}
                      </div>
                    )}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-tertiary transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
              </Link>
            );
          })
        ) : (
          <div className="text-sm rounded-xl border border-dashed border-subtle bg-surface-2 px-3 py-4 text-tertiary">
            No issues matched the current request.
          </div>
        )}
      </div>

      {remainingIssues > 0 && (
        <div className="mt-3 text-11 text-tertiary">
          +{remainingIssues} more issue{remainingIssues === 1 ? "" : "s"}
        </div>
      )}
    </div>
  );
}
