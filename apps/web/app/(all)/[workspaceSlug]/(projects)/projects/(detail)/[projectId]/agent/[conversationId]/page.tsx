/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { PageHead } from "@/components/core/page-title";
import { AgentThreadShell } from "@/components/agent";
import { useProject } from "@/hooks/store/use-project";
import type { Route } from "./+types/page";

function ProjectAgentConversationPage({ params }: Route.ComponentProps) {
  const { workspaceSlug, projectId, conversationId } = params;
  const { getProjectById } = useProject();
  const project = getProjectById(projectId);
  const pageTitle = project?.name ? `${project.name} - Agent` : "Project Agent";

  return (
    <>
      <PageHead title={pageTitle} />
      <AgentThreadShell
        workspaceSlug={workspaceSlug}
        projectId={projectId}
        conversationId={conversationId}
        title={project?.name ?? "Project Agent"}
        subtitle="Project agent"
      />
    </>
  );
}

export default observer(ProjectAgentConversationPage);
