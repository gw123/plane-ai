/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { getAgentToolRenderModels, getAgentUnsupportedToolResultFallbackText } from "./tool-renderer-registry.ts";

test("getAgentToolRenderModels maps create_issue outputs to IssueCreatedCard models", () => {
  const renderModels = getAgentToolRenderModels([
    {
      call_id: "call-create-1",
      tool_name: "create_issue",
      success: true,
      output: {
        id: "issue-1",
        project_id: "project-1",
        display_id: "PROJ-12",
        name: "Fix login crash",
        priority: "high",
        state: {
          id: "state-1",
          name: "Backlog",
          group: "backlog",
          color: "#60646C",
        },
      },
      error: null,
    },
  ]);

  assert.deepEqual(renderModels, [
    {
      kind: "create_issue",
      callId: "call-create-1",
      toolName: "create_issue",
      output: {
        id: "issue-1",
        project_id: "project-1",
        display_id: "PROJ-12",
        name: "Fix login crash",
        priority: "high",
        state: {
          id: "state-1",
          name: "Backlog",
          group: "backlog",
          color: "#60646C",
        },
      },
    },
  ]);
});

test("getAgentToolRenderModels maps list_projects outputs to ProjectListCard models", () => {
  const renderModels = getAgentToolRenderModels([
    {
      call_id: "call-projects-1",
      tool_name: "list_projects",
      success: true,
      output: {
        count: 2,
        projects: [
          {
            id: "project-1",
            identifier: "ALPHA",
            name: "Alpha",
            logo_props: null,
            is_archived: false,
          },
          {
            id: "project-2",
            identifier: "BETA",
            name: "Beta",
            logo_props: null,
            is_archived: true,
          },
        ],
      },
      error: null,
    },
  ]);

  assert.equal(renderModels[0]?.kind, "list_projects");
  assert.equal(renderModels[0]?.toolName, "list_projects");
  assert.equal(renderModels[0]?.output.count, 2);
});

test("getAgentToolRenderModels maps list_issues outputs to IssueListCard models", () => {
  const renderModels = getAgentToolRenderModels([
    {
      call_id: "call-issues-1",
      tool_name: "list_issues",
      success: true,
      output: {
        count: 2,
        issues: [
          {
            id: "issue-1",
            display_id: "ALPHA-1",
            name: "Fix login crash",
            priority: "high",
            start_date: null,
            target_date: "2026-04-30",
            state: {
              id: "state-1",
              name: "Backlog",
              group: "backlog",
              color: "#60646C",
            },
          },
          {
            id: "issue-2",
            display_id: "ALPHA-2",
            name: "Polish onboarding copy",
            priority: "medium",
            start_date: "2026-04-25",
            target_date: null,
            state: {
              id: "state-2",
              name: "In Progress",
              group: "started",
              color: "#2563EB",
            },
          },
        ],
      },
      error: null,
    },
  ]);

  assert.equal(renderModels[0]?.kind, "list_issues");
  assert.equal(renderModels[0]?.toolName, "list_issues");
  assert.equal(renderModels[0]?.output.count, 2);
  assert.equal(renderModels[0]?.output.issues[0]?.display_id, "ALPHA-1");
});

test("getAgentToolRenderModels maps failed tool results to error cards", () => {
  const renderModels = getAgentToolRenderModels([
    {
      call_id: "call-create-1",
      tool_name: "create_issue",
      success: false,
      output: null,
      error: {
        code: "AGENT_TOOL_FORBIDDEN",
        message: "You do not have permission to create issues in this project.",
      },
    },
  ]);

  assert.deepEqual(renderModels, [
    {
      kind: "error",
      callId: "call-create-1",
      toolName: "create_issue",
      error: {
        code: "AGENT_TOOL_FORBIDDEN",
        message: "You do not have permission to create issues in this project.",
      },
    },
  ]);
});

test("getAgentToolRenderModels ignores unsupported success payloads", () => {
  const renderModels = getAgentToolRenderModels([
    {
      call_id: "call-unknown-1",
      tool_name: "unknown_tool",
      success: true,
      output: {
        foo: "bar",
      },
      error: null,
    },
  ]);

  assert.deepEqual(renderModels, []);
});

test("getAgentUnsupportedToolResultFallbackText returns a generic fallback for unsupported successful tools", () => {
  const fallbackText = getAgentUnsupportedToolResultFallbackText([
    {
      call_id: "call-search-1",
      tool_name: "search_issues",
      success: true,
      output: {
        count: 3,
      },
      error: null,
    },
  ]);

  assert.equal(fallbackText, "Completed search issues.");
});

test("getAgentUnsupportedToolResultFallbackText ignores supported cards and failures", () => {
  const fallbackText = getAgentUnsupportedToolResultFallbackText([
    {
      call_id: "call-projects-1",
      tool_name: "list_projects",
      success: true,
      output: {
        count: 1,
        projects: [
          {
            id: "project-1",
            identifier: "ALPHA",
            name: "Alpha",
            logo_props: null,
            is_archived: false,
          },
        ],
      },
      error: null,
    },
    {
      call_id: "call-create-1",
      tool_name: "create_issue",
      success: false,
      output: null,
      error: {
        code: "AGENT_TOOL_FORBIDDEN",
        message: "You do not have permission to create issues in this project.",
      },
    },
  ]);

  assert.equal(fallbackText, null);
});
