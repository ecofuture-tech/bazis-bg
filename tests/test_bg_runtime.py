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

import logging
import os
import time
from datetime import UTC, datetime, timedelta
from zipfile import ZipFile

from django.core.management import call_command
from django.utils.timezone import now

import pytest
from entity.bg.calc_data import ExportParents, LogMessage

from bazis.contrib.bg.bg.tasks_clean import BgTasksClean
from bazis.contrib.bg.management.commands.bg_scheduler import Command as Scheduler
from bazis.contrib.bg.management.commands.bg_scheduler import cron_next_run
from bazis.contrib.bg.models import Task

from tests import factories


def _run(task):
    call_command('bg_task', task_id=task.id)
    task.refresh_from_db()
    return task


@pytest.mark.django_db(transaction=True)
def test_task_logs_are_separate():
    """
    A handler process runs many tasks: the log of a task must not collect the records of
    the next ones, and the handlers of finished tasks must be removed.
    """
    root_handlers = list(logging.getLogger().handlers)

    first = _run(LogMessage.delay('first'))
    second = _run(LogMessage.delay('second'))

    assert first.is_success and second.is_success
    assert 'message: first' in first.log
    assert 'message: second' not in first.log
    assert 'message: second' in second.log
    assert 'message: first' not in second.log
    assert logging.getLogger().handlers == root_handlers


@pytest.mark.django_db(transaction=True)
def test_export_split_into_zip(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = str(tmp_path)
    factories.ParentEntityFactory.create_batch(5, child_entities=False)
    monkeypatch.setattr(ExportParents, 'limit_rows_split', 2)

    task = _run(ExportParents.delay())

    assert task.is_success, task.error
    assert task.file.name.endswith('.zip')
    assert task.file_params['total_count'] == 5
    with ZipFile(task.file.path) as zp:
        # 5 rows by 2 per workbook
        assert len(zp.namelist()) == 3


@pytest.mark.django_db(transaction=True)
def test_scheduler_starts_oldest_tasks_within_parallel_limit():
    scheduler = Scheduler()
    tasks = [LogMessage.delay(str(i)) for i in range(4)]
    # make the creation order explicit
    for i, task in enumerate(tasks):
        Task.objects.filter(pk=task.pk).update(dt_created=now() - timedelta(minutes=10 - i))

    scheduler.tasks_prepare()
    states = {t.pk: t.state for t in Task.objects.all()}
    # LogMessage.parallel == 2: the two oldest start
    assert [states[t.pk] for t in tasks] == ['starting', 'starting', 'waiting', 'waiting']

    # finishing one task lets the next oldest start
    Task.objects.get(pk=tasks[0].pk).set_done('completed')
    scheduler.tasks_prepare()
    states = {t.pk: t.state for t in Task.objects.all()}
    assert [states[t.pk] for t in tasks] == ['done', 'starting', 'starting', 'waiting']


def test_cron_next_run_is_utc():
    """
    The next run time does not depend on the time zone of the server.
    """
    tz = os.environ.get('TZ')
    os.environ['TZ'] = 'Asia/Tokyo'
    time.tzset()
    try:
        dt_run = cron_next_run('0 * * * *')
    finally:
        if tz is None:
            os.environ.pop('TZ')
        else:
            os.environ['TZ'] = tz
        time.tzset()

    utc_now = datetime.now(UTC)
    assert dt_run.tzinfo is not None
    assert dt_run.minute == 0
    assert timedelta(0) < dt_run - utc_now <= timedelta(hours=1)


@pytest.mark.django_db(transaction=True)
def test_tasks_clean_deletes_files(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    factories.ParentEntityFactory.create_batch(2, child_entities=False)
    old = _run(ExportParents.delay())
    path = old.file.path
    assert os.path.exists(path)
    # dt_updated is set by a trigger: every finished task is older than a zero lifetime
    settings.BAZIS_TASK_LIFETIME = 0

    clean = _run(BgTasksClean.delay())

    assert clean.is_success, clean.error
    assert not Task.objects.filter(pk=old.pk).exists()
    assert not os.path.exists(path)


@pytest.mark.django_db(transaction=True)
def test_scheduler_blocked_backlog_does_not_starve_other_classes(monkeypatch):
    """
    More waiting tasks of a saturated class than the batch must not keep the tasks of other
    classes from starting.
    """
    scheduler = Scheduler()
    monkeypatch.setattr(Scheduler, 'prepare_batch', 3)
    backlog = [LogMessage.delay(str(i)) for i in range(6)]
    for i, task in enumerate(backlog):
        Task.objects.filter(pk=task.pk).update(dt_created=now() - timedelta(hours=1, minutes=i))
    scheduler.tasks_prepare()
    # LogMessage.parallel == 2: the class is saturated now
    assert Task.objects.filter(state='starting').count() == 2

    export = ExportParents.delay()
    scheduler.tasks_prepare()

    export.refresh_from_db()
    assert export.state == 'starting'
    assert Task.objects.filter(cls_path=backlog[0].cls_path, state='starting').count() == 2
    assert set(
        Task.objects.filter(state='waiting').values_list('phase', flat=True)
    ) == {'Maximum of 2 similar tasks'}
