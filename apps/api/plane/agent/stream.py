# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json

from django.core.serializers.json import DjangoJSONEncoder


def encode_sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, cls=DjangoJSONEncoder)}\n\n"
