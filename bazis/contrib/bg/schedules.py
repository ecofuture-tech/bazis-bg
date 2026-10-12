# Copyright 2026 EcoFuture Technology Services LLC and contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
The periodic tasks of bazis-bg, applied by `migrate` (`bazis.contrib.bg.declare`): the
cleanup of the tasks not updated for `BAZIS_TASK_LIFETIME` (manual) or
`BAZIS_TASK_CRON_LIFETIME` (periodic) seconds, every `BAZIS_TASK_CRON_CLEANUP` seconds,
unless `BAZIS_TASK_CLEANUP` is false.
"""

from django.conf import settings

from .declare import Schedule


SCHEDULES = [
    Schedule(
        'bg_tasks_clean',
        'bazis.contrib.bg.bg.tasks_clean.BgTasksClean',
        settings.BAZIS_TASK_CRON_CLEANUP,
        enabled=settings.BAZIS_TASK_CLEANUP,
    ),
]
