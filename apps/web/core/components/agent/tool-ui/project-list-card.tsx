/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { FolderKanban } from "lucide-react";
import { Logo } from "@plane/propel/emoji-icon-picker";
import { cn } from "@plane/utils";
import type { TAgentToolRenderModel } from "./tool-renderer-registry";
import { hasConfiguredProjectLogo } from "./project-list-card.helpers";

type ProjectListCardProps = {
  result: Extract<TAgentToolRenderModel, { kind: "list_projects" }>;
};

const MAX_VISIBLE_PROJECTS = 5;

export function ProjectListCard(props: ProjectListCardProps) {
  const {
    result: { output },
  } = props;
  const visibleProjects = output.projects.slice(0, MAX_VISIBLE_PROJECTS);
  const remainingProjects = Math.max(output.projects.length - visibleProjects.length, 0);

  return (
    <div className="shadow-sm w-full rounded-2xl border border-subtle bg-surface-1 p-4 text-primary">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="text-11 font-medium tracking-[0.12em] text-secondary uppercase">Projects</div>
          <div className="text-sm mt-1 font-semibold">
            {output.count} visible project{output.count === 1 ? "" : "s"}
          </div>
        </div>
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-surface-2 text-secondary">
          <FolderKanban className="h-4 w-4" />
        </div>
      </div>

      <div className="mt-3 space-y-2">
        {visibleProjects.length > 0 ? (
          visibleProjects.map((project) => (
            <div
              key={project.id}
              className="flex items-center gap-3 rounded-xl border border-subtle bg-surface-2 px-3 py-2"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface-1">
                {hasConfiguredProjectLogo(project.logo_props) ? (
                  <Logo logo={project.logo_props ?? undefined} size={18} />
                ) : (
                  <FolderKanban className="h-4 w-4 text-secondary" />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm truncate font-medium">{project.name}</div>
                <div className="truncate text-11 text-tertiary">{project.identifier}</div>
              </div>
              {project.is_archived && (
                <span
                  className={cn(
                    "rounded-full border border-subtle bg-surface-1 px-2 py-1 text-11 font-medium text-tertiary"
                  )}
                >
                  Archived
                </span>
              )}
            </div>
          ))
        ) : (
          <div className="text-sm rounded-xl border border-dashed border-subtle bg-surface-2 px-3 py-4 text-tertiary">
            No visible projects were returned.
          </div>
        )}
      </div>

      {remainingProjects > 0 && (
        <div className="mt-3 text-11 text-tertiary">
          +{remainingProjects} more project{remainingProjects === 1 ? "" : "s"}
        </div>
      )}
    </div>
  );
}
