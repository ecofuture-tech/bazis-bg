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

from datetime import timedelta

from django.conf import settings
from django.utils.timezone import now

from ..basic.base import BgBase
from ..models import Task


class BgTasksClean(BgBase):
    name = 'Background tasks cleanup'
    parallel = 1

    def handle(self):
        # get all manual tasks that have not been updated for longer than the specified period
        qs = Task.objects.filter(
            dt_updated__lt=(now() - timedelta(seconds=settings.BAZIS_TASK_LIFETIME)),
            task_cron__isnull=True,
        )
        self.next_phase('Manual tasks cleanup', expected=qs.count())
        qs._raw_delete(qs.db)

        # get all periodic tasks that have not been updated for longer than the specified period
        qs = Task.objects.filter(
            dt_updated__lt=(now() - timedelta(seconds=settings.BAZIS_TASK_CRON_LIFETIME)),
            task_cron__isnull=False,
        )
        self.next_phase('Periodic tasks cleanup', expected=qs.count())
        qs._raw_delete(qs.db)
