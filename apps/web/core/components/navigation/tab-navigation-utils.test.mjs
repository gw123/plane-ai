/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { getTabUrl } from "./tab-navigation-utils.ts";

test("getTabUrl maps the agent tab to the project agent route", () => {
  assert.equal(getTabUrl("plane", "project-1", "agent"), "/plane/projects/project-1/agent");
});

test("getTabUrl keeps unknown tabs on the work items fallback", () => {
  assert.equal(getTabUrl("plane", "project-1", "unknown"), "/plane/projects/project-1/issues");
});
