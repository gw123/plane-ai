# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone

from plane.bgtasks.issue_activities_task import issue_activity


def enqueue_issue_created_activity(
    *,
    requested_data: dict | None,
    actor_id: str,
    issue_id: str,
    project_id: str,
    origin: str | None = None,
    intake: str | None = None,
) -> None:
    issue_activity.delay(
        type="issue.activity.created",
        requested_data=json.dumps(requested_data, cls=DjangoJSONEncoder),
        actor_id=str(actor_id),
        issue_id=str(issue_id),
        project_id=str(project_id),
        current_instance=None,
        epoch=int(timezone.now().timestamp()),
        notification=True,
        origin=origin,
        intake=intake,
    )
