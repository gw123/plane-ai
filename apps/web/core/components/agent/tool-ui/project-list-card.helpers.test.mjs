/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import assert from "node:assert/strict";
import test from "node:test";
import { hasConfiguredProjectLogo } from "./project-list-card.helpers.ts";

test("hasConfiguredProjectLogo returns false for empty logo_props objects", () => {
  assert.equal(hasConfiguredProjectLogo({}), false);
});

test("hasConfiguredProjectLogo returns true when in_use is configured", () => {
  assert.equal(
    hasConfiguredProjectLogo({
      in_use: "emoji",
      emoji: { value: "128640" },
    }),
    true
  );
});
