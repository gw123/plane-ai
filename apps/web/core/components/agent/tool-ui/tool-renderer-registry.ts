/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { IAgentToolError, IAgentToolResult, TIssuePriorities, TLogoProps, TStateGroups } from "@plane/types";

type TCreateIssueCardOutput = {
  id: string;
  project_id: string;
  display_id: string;
  name: string;
  priority: TIssuePriorities;
  state: {
    id: string;
    name: string;
    group: TStateGroups;
    color: string;
  };
};

type TProjectListCardProject = {
  id: string;
  identifier: string;
  name: string;
  logo_props: TLogoProps | null;
  is_archived: boolean;
};

type TProjectListCardOutput = {
  count: number;
  projects: TProjectListCardProject[];
};

export type TAgentToolRenderModel =
  | {
      kind: "create_issue";
      callId: string;
      toolName: "create_issue";
      output: TCreateIssueCardOutput;
    }
  | {
      kind: "list_projects";
      callId: string;
      toolName: "list_projects";
      output: TProjectListCardOutput;
    }
  | {
      kind: "error";
      callId: string;
      toolName: string;
      error: IAgentToolError;
    };

const formatToolName = (toolName: string) => toolName.split("_").join(" ");

const STATE_GROUPS = new Set<TStateGroups>(["backlog", "unstarted", "started", "completed", "cancelled"]);

const isRecord = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null;

const isString = (value: unknown): value is string => typeof value === "string";

const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";

const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

const ISSUE_PRIORITIES = new Set<TIssuePriorities>(["urgent", "high", "medium", "low", "none"]);

const isNullableLogoProps = (value: unknown): value is TLogoProps | null => {
  if (value === null) return true;
  return isRecord(value);
};

const isAgentToolError = (value: unknown): value is IAgentToolError => {
  return isRecord(value) && isString(value.code) && isString(value.message);
};

const normalizeToolError = (toolName: string, error: unknown): IAgentToolError => {
  if (isAgentToolError(error)) return error;

  return {
    code: "AGENT_TOOL_EXECUTION_ERROR",
    message: `${toolName} failed without a structured error payload.`,
  };
};

const isCreateIssueCardOutput = (value: unknown): value is TCreateIssueCardOutput => {
  if (!isRecord(value)) return false;
  if (
    !isString(value.id) ||
    !isString(value.project_id) ||
    !isString(value.display_id) ||
    !isString(value.name) ||
    !isString(value.priority) ||
    !ISSUE_PRIORITIES.has(value.priority as TIssuePriorities)
  ) {
    return false;
  }

  const state = value.state;
  if (!isRecord(state)) return false;

  return (
    isString(state.id) &&
    isString(state.name) &&
    isString(state.group) &&
    STATE_GROUPS.has(state.group as TStateGroups) &&
    isString(state.color)
  );
};

const isProjectListCardProject = (value: unknown): value is TProjectListCardProject => {
  if (!isRecord(value)) return false;

  return (
    isString(value.id) &&
    isString(value.identifier) &&
    isString(value.name) &&
    isNullableLogoProps(value.logo_props) &&
    isBoolean(value.is_archived)
  );
};

const isProjectListCardOutput = (value: unknown): value is TProjectListCardOutput => {
  if (!isRecord(value)) return false;
  if (!isNumber(value.count) || !Array.isArray(value.projects)) return false;

  return value.projects.every(isProjectListCardProject);
};

const toAgentToolRenderModel = (toolResult: IAgentToolResult): TAgentToolRenderModel | null => {
  if (!toolResult.success) {
    return {
      kind: "error",
      callId: toolResult.call_id,
      toolName: toolResult.tool_name,
      error: normalizeToolError(toolResult.tool_name, toolResult.error),
    };
  }

  if (toolResult.tool_name === "create_issue" && isCreateIssueCardOutput(toolResult.output)) {
    return {
      kind: "create_issue",
      callId: toolResult.call_id,
      toolName: "create_issue",
      output: toolResult.output,
    };
  }

  if (toolResult.tool_name === "list_projects" && isProjectListCardOutput(toolResult.output)) {
    return {
      kind: "list_projects",
      callId: toolResult.call_id,
      toolName: "list_projects",
      output: toolResult.output,
    };
  }

  return null;
};

export const getAgentToolRenderModels = (
  toolResults: IAgentToolResult[] | null | undefined
): TAgentToolRenderModel[] => {
  if (!toolResults?.length) return [];

  const renderModels: TAgentToolRenderModel[] = [];

  toolResults.forEach((toolResult) => {
    const renderModel = toAgentToolRenderModel(toolResult);
    if (renderModel) {
      renderModels.push(renderModel);
    }
  });

  return renderModels;
};

export const getAgentUnsupportedToolResultFallbackText = (
  toolResults: IAgentToolResult[] | null | undefined
): string | null => {
  if (!toolResults?.length) return null;

  const unsupportedToolNames = toolResults.flatMap((toolResult) => {
    if (!toolResult.success || toAgentToolRenderModel(toolResult)) return [];
    return [formatToolName(toolResult.tool_name)];
  });

  if (!unsupportedToolNames.length) return null;

  if (unsupportedToolNames.length === 1) {
    return `Completed ${unsupportedToolNames[0]}.`;
  }

  return `Completed tool calls: ${unsupportedToolNames.join(", ")}.`;
};
