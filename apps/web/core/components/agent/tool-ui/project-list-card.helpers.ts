/**
 * Copyright (c) 2023-present Plane Software, Inc. and contributors
 * SPDX-License-Identifier: AGPL-3.0-only
 * See the LICENSE file for details.
 */

import type { TLogoProps } from "@plane/types";

export const hasConfiguredProjectLogo = (logoProps: TLogoProps | null | undefined): boolean =>
  logoProps?.in_use === "emoji" || logoProps?.in_use === "icon";
