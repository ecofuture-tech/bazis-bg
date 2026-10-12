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
from entity.models import Report, TaskArchive

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


def _old_export(settings, tmp_path):
    """
    A finished export with a file, older than the lifetime of the manual tasks (1 second).
    """
    settings.MEDIA_ROOT = str(tmp_path)
    factories.ParentEntityFactory.create_batch(2, child_entities=False)
    export = _run(ExportParents.delay())
    assert os.path.exists(export.file.path)
    settings.BAZIS_TASK_LIFETIME = 1
    time.sleep(1.1)
    return export


@pytest.mark.django_db(transaction=True)
def test_tasks_clean_applies_the_foreign_keys_to_the_tasks(settings, tmp_path):
    """
    A report references an old task (SET_NULL): the cleanup unlinks it and deletes the task
    and its file. A raw delete of the rows failed on the foreign key, after the files were
    deleted, at every run.
    """
    export = _old_export(settings, tmp_path)
    report = Report.objects.create(title='Report', task=export)

    clean = _run(BgTasksClean.delay())

    assert clean.is_success, clean.error
    assert not Task.objects.filter(pk=export.pk).exists()
    assert not os.path.exists(export.file.path)
    report.refresh_from_db()
    assert report.task is None


@pytest.mark.django_db(transaction=True)
def test_tasks_clean_leaves_the_protected_tasks(settings, tmp_path):
    """
    A task kept by a PROTECT foreign key stays with its file and is logged; the other tasks
    of its portion are deleted.
    """
    export = _old_export(settings, tmp_path)
    other = _run(LogMessage.delay('old'))
    time.sleep(1.1)
    TaskArchive.objects.create(task=export)

    clean = _run(BgTasksClean.delay())

    assert clean.is_success, clean.error
    assert list(Task.objects.exclude(pk=clean.pk).values_list('pk', flat=True)) == [export.pk]
    assert os.path.exists(export.file.path)
    assert not Task.objects.filter(pk=other.pk).exists()
    assert f'The task {export.pk} is kept by a protected reference' in clean.log


@pytest.mark.django_db(transaction=True)
def test_tasks_clean_deletes_the_rows_when_the_storage_fails(settings, tmp_path, monkeypatch):
    """
    The rows are deleted first; a file the storage fails to delete is logged and left.
    """
    export = _old_export(settings, tmp_path)
    storage = Task._meta.get_field('file').storage

    def failing_delete(name):
        raise OSError('the storage is down')

    monkeypatch.setattr(type(storage), 'delete', lambda self, name: failing_delete(name))

    clean = _run(BgTasksClean.delay())

    assert clean.is_success, clean.error
    assert not Task.objects.filter(pk=export.pk).exists()
    assert os.path.exists(export.file.path)
    assert f'The file {export.file.name} of a task was not deleted' in clean.log


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


def test_load_zip_skips_macos_metadata(tmp_path):
    """
    Archives made on macOS contain `__MACOSX/._<name>.xlsx` metadata files, which are not
    workbooks.
    """
    from openpyxl import Workbook

    from bazis.contrib.bg.basic.base_load import BgBaseLoad

    workbook = Workbook()
    workbook.active.append(['a', 1])
    xlsx = tmp_path / 'data.xlsx'
    workbook.save(xlsx)
    archive = tmp_path / 'data.zip'
    with ZipFile(archive, 'w') as zp:
        zp.write(xlsx, 'data.xlsx')
        zp.writestr('__MACOSX/._data.xlsx', b'\x00\x05\x16\x07')
        zp.writestr('._other.xlsx', b'\x00')

    rows = []

    class Load(BgBaseLoad):
        fields_read = ['name', 'value']

        def __init__(self):
            self.log = logging.getLogger(__name__)

        def task_file_get(self):
            return open(archive, 'rb')  # noqa: SIM115

        def next_phase(self, *args, **kwargs): ...

        def progress(self, *args, **kwargs): ...

        def load(self, reader):
            rows.extend(reader)

    Load().handle()
    assert rows == [{'name': 'a', 'value': 1}]
