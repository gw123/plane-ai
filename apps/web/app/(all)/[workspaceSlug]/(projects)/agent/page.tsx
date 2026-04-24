/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { observer } from "mobx-react";
import { PageHead } from "@/components/core/page-title";
import { AgentThreadShell } from "@/components/agent";
import { useWorkspace } from "@/hooks/store/use-workspace";
import type { Route } from "./+types/page";

function WorkspaceAgentPage({ params }: Route.ComponentProps) {
  const { workspaceSlug } = params;
  const { currentWorkspace } = useWorkspace();
  const pageTitle = currentWorkspace?.name ? `${currentWorkspace.name} - Agent` : "Plane Agent";

  return (
    <>
      <PageHead title={pageTitle} />
      <AgentThreadShell
        workspaceSlug={workspaceSlug}
        title={currentWorkspace?.name ?? "Plane Agent"}
        subtitle="Workspace agent"
      />
    </>
  );
}

export default observer(WorkspaceAgentPage);
