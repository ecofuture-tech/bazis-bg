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

    def delete_tasks(self, qs, chunk_size=1000):
        # the rows are fixed first: a task that ages between the two queries would lose
        # its row but keep its file. The files of the tasks are deleted from the storage,
        # then the rows (raw delete: fast, without signals, which would leave the files)
        pks = list(qs.values_list('pk', flat=True))
        storage = Task._meta.get_field('file').storage
        for i in range(0, len(pks), chunk_size):
            chunk = Task.objects.filter(pk__in=pks[i : i + chunk_size])
            for name in chunk.exclude(file='').exclude(file=None).values_list('file', flat=True):
                try:
                    storage.delete(name)
                except Exception:  # NOQA [B902]
                    self.log.warning('The file %s of a task was not deleted', name)
            chunk._raw_delete(chunk.db)

    def handle(self):
        # get all manual tasks that have not been updated for longer than the specified period
        qs = Task.objects.filter(
            dt_updated__lt=(now() - timedelta(seconds=settings.BAZIS_TASK_LIFETIME)),
            task_cron__isnull=True,
        ).exclude(pk=self.task_id)
        self.next_phase('Manual tasks cleanup', expected=qs.count())
        self.delete_tasks(qs)

        # get all periodic tasks that have not been updated for longer than the specified period
        qs = Task.objects.filter(
            dt_updated__lt=(now() - timedelta(seconds=settings.BAZIS_TASK_CRON_LIFETIME)),
            task_cron__isnull=False,
        ).exclude(pk=self.task_id)
        self.next_phase('Periodic tasks cleanup', expected=qs.count())
        self.delete_tasks(qs)
