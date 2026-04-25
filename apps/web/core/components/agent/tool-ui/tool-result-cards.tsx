/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import { IssueCreatedCard } from "./issue-created-card";
import { IssueListCard } from "./issue-list-card";
import { ProjectListCard } from "./project-list-card";
import { ToolErrorCard } from "./tool-error-card";
import type { TAgentToolRenderModel } from "./tool-renderer-registry";

type AgentToolResultCardsProps = {
  renderModels: TAgentToolRenderModel[];
};

export function AgentToolResultCards(props: AgentToolResultCardsProps) {
  const { renderModels } = props;

  if (renderModels.length === 0) return null;

  return (
    <div className="w-full space-y-3">
      {renderModels.map((result) => {
        if (result.kind === "create_issue") {
          return <IssueCreatedCard key={`${result.callId}:${result.kind}`} result={result} />;
        }

        if (result.kind === "list_projects") {
          return <ProjectListCard key={`${result.callId}:${result.kind}`} result={result} />;
        }

        if (result.kind === "list_issues") {
          return <IssueListCard key={`${result.callId}:${result.kind}`} result={result} />;
        }

        return <ToolErrorCard key={`${result.callId}:${result.kind}`} result={result} />;
      })}
    </div>
  );
}
