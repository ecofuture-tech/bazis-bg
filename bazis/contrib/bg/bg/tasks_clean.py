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
from django.db import transaction
from django.db.models import ProtectedError, RestrictedError
from django.utils.timezone import now

from ..basic.base import BgBase
from ..models import Task


class BgTasksClean(BgBase):
    name = 'Background tasks cleanup'
    parallel = 1
    # each portion of tasks is deleted in a transaction of its own, committed before the
    # files of its tasks are deleted from the storage
    is_transaction = False

    def delete_tasks(self, qs, chunk_size=1000):
        """
        Deletes the tasks of `qs` by portions of `chunk_size` through the ORM, so that the
        `on_delete` of the foreign keys to the tasks applies (SET_NULL, CASCADE), each portion
        in a transaction; then the files of the deleted tasks from the storage (a file that
        fails is logged and left). A task that a PROTECT or RESTRICT foreign key keeps is
        logged and left with its file, the other tasks of its portion are deleted one by one.
        """
        # the rows are fixed first: a task that ages meanwhile waits for the next run
        pks = list(qs.values_list('pk', flat=True))
        for i in range(0, len(pks), chunk_size):
            chunk = pks[i : i + chunk_size]
            try:
                files = self._delete_rows(chunk)
            except (ProtectedError, RestrictedError):
                files = []
                for pk in chunk:
                    try:
                        files += self._delete_rows([pk])
                    except (ProtectedError, RestrictedError):
                        self.log.warning('The task %s is kept by a protected reference', pk)
            storage = Task._meta.get_field('file').storage
            for name in files:
                try:
                    storage.delete(name)
                except Exception:  # NOQA [B902]
                    self.log.warning('The file %s of a task was not deleted', name)

    @staticmethod
    def _delete_rows(pks) -> list[str]:
        """
        Deletes the tasks in a transaction and returns the names of their files.
        """
        with transaction.atomic():
            # only the keys are loaded when the deletion needs the objects (the signals or
            # the foreign keys to them): not the logs
            tasks = Task.objects.filter(pk__in=pks).only('pk')
            files = list(tasks.exclude(file='').exclude(file=None).values_list('file', flat=True))
            tasks.delete()
        return files

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
