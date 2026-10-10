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
The periodic tasks declared in the code (`schedules.py`, bazis.contrib.bg.declare), which
`migrate` applies; the sample declares `entity_log_hourly` (entity/schedules.py).
"""

import logging
from datetime import timedelta

from django.contrib.admin.sites import AdminSite
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import RequestFactory
from django.utils.timezone import now

import pytest
from bazis_test_utils import plugin
from entity.bg.calc_data import LogMessage

from bazis.contrib.bg import declare
from bazis.contrib.bg.admin import TaskCronAdmin
from bazis.contrib.bg.checks import check_declarations, check_declarations_applied
from bazis.contrib.bg.declare import Schedule, apply_declarations, declaration_messages
from bazis.contrib.bg.models import Task, TaskCron


LOG_MESSAGE = 'entity.bg.calc_data.LogMessage'
#: the schedule of the sample
SAMPLE = declare.declarations()


def apply(*schedules, dry_run=False):
    """
    Applies the schedules of the sample and these ones.
    """
    return apply_declarations(schedules=[*SAMPLE, *schedules], dry_run=dry_run)


def errors(*schedules):
    return [(it.id, it.msg) for it in declaration_messages([('test', it) for it in schedules])]


@pytest.mark.django_db
def test_migrate_creates_the_declared_periodic_task():
    cron = TaskCron.objects.get(slug='entity_log_hourly')
    assert cron.managed and cron.is_enable
    assert (cron.name, cron.cls_path, cron.period) == ('Log a message hourly', LOG_MESSAGE, '3600')
    assert (cron.args, cron.kwargs) == (None, {'message': 'hourly'})
    # the database is as declared: applied again, nothing changes
    assert apply_declarations() == []
    assert check_declarations(None) == []
    assert check_declarations_applied(None, databases=['default']) == []


@pytest.mark.django_db
def test_a_declared_schedule_is_created_and_updated(monkeypatch):
    nightly = Schedule('nightly_log', LogMessage, '0 3 * * *', 'Nightly log', kwargs={'message': 'night'})
    # the database check sees the missing periodic task
    assert apply(nightly, dry_run=True) == ['taskcron nightly_log: created']
    assert not TaskCron.objects.filter(slug='nightly_log').exists()
    with monkeypatch.context() as patch:
        patch.setattr(declare, 'declarations', lambda: [*SAMPLE, ('test', nightly)])
        [warning] = check_declarations_applied(None, databases=['default'])
    assert (warning.id, warning.msg) == (
        'bg.W001', 'The database default differs from the declared schedules: taskcron nightly_log: created.'
    )

    assert apply(nightly) == ['taskcron nightly_log: created']
    cron = TaskCron.objects.get(slug='nightly_log')
    # a task class is stored as its path
    assert (cron.cls_path, cron.period, cron.kwargs, cron.managed) == (
        LOG_MESSAGE, '0 3 * * *', {'message': 'night'}, True
    )
    assert apply(nightly) == []

    # the next run time the scheduler computed is kept while the period stays
    dt_run = now() + timedelta(hours=1)
    TaskCron.objects.filter(pk=cron.pk).update(dt_run=dt_run)
    renamed = Schedule('nightly_log', LogMessage, '0 3 * * *', 'Night log', kwargs={'message': 'night'})
    assert apply(renamed) == ['taskcron nightly_log: name changed']
    cron.refresh_from_db()
    assert (cron.name, cron.dt_run) == ('Night log', dt_run)

    # a new period: the scheduler computes the next run again
    earlier = Schedule('nightly_log', LogMessage, '0 2 * * *', 'Night log', kwargs={'message': 'night'})
    assert apply(earlier) == ['taskcron nightly_log: period changed']
    cron.refresh_from_db()
    assert (cron.period, cron.dt_run) == ('0 2 * * *', None)

    # disabled in the code
    TaskCron.objects.filter(pk=cron.pk).update(dt_run=dt_run)
    off = Schedule('nightly_log', LogMessage, '0 2 * * *', 'Night log', {'message': 'night'}, enabled=False)
    assert apply(off) == ['taskcron nightly_log: is_enable changed']
    cron.refresh_from_db()
    assert (cron.is_enable, cron.dt_run) == (False, None)


@pytest.mark.django_db
def test_the_name_of_the_task_class_without_a_name():
    apply(Schedule('unnamed_log', LOG_MESSAGE, 60, kwargs={'message': 'm'}))
    assert TaskCron.objects.get(slug='unnamed_log').name == 'Log message'


@pytest.mark.django_db
def test_an_unmarked_periodic_task_of_the_slug_is_taken_over(caplog):
    cron = TaskCron.objects.create(
        slug='admin_log', name='Admin log', cls_path=LOG_MESSAGE, period='60', args=['x'], dt_run=now()
    )

    with caplog.at_level(logging.WARNING, logger='bazis.core.declare'):
        changes = apply(Schedule('admin_log', LOG_MESSAGE, 120, 'Declared log', {'message': 'm'}))

    assert changes == ['taskcron admin_log: name, period, args, kwargs, managed changed']
    assert 'taskcron admin_log exists and is not managed' in caplog.text
    cron.refresh_from_db()
    assert cron.managed
    assert (cron.name, cron.period, cron.args, cron.kwargs, cron.dt_run) == (
        'Declared log', '120', None, {'message': 'm'}, None
    )


@pytest.mark.django_db
def test_a_periodic_task_no_longer_declared_is_disabled():
    temporary = Schedule('temporary_log', LOG_MESSAGE, 60, 'Temporary', {'message': 't'})
    apply(temporary)
    cron = TaskCron.objects.get(slug='temporary_log')
    task = LogMessage.delay('t')
    Task.objects.filter(pk=task.pk).update(task_cron=cron)
    # the periodic tasks of the admin (not managed) are not the ones of the code
    admin_cron = TaskCron.objects.create(name='Admin', cls_path=LOG_MESSAGE, period='60')

    assert apply(dry_run=True) == ['taskcron temporary_log: disabled, no longer declared']
    [warning] = check_declarations_applied(None, databases=['default'])
    assert warning.id == 'bg.W001'
    assert 'taskcron temporary_log: disabled, no longer declared' in warning.msg

    assert apply() == ['taskcron temporary_log: disabled, no longer declared']
    cron.refresh_from_db()
    # kept for its tasks, an ordinary periodic task now
    assert (cron.is_enable, cron.managed) == (False, False)
    assert Task.objects.get(pk=task.pk).task_cron == cron
    admin_cron.refresh_from_db()
    assert admin_cron.is_enable and not admin_cron.managed
    assert apply() == []
    assert check_declarations_applied(None, databases=['default']) == []

    # declared again: taken over
    assert apply(temporary) == ['taskcron temporary_log: is_enable, managed changed']


def test_the_declarations_are_checked():
    assert errors(Schedule('ok', LOG_MESSAGE, '*/5 * * * *', 'Ok', {'message': 'm'})) == []
    assert errors(Schedule('bad_path', 'entity.bg.calc_data.Missing', 60, 'Bad', {})) == [
        ('bg.E002', "The schedule bad_path: the task 'entity.bg.calc_data.Missing' does not import: "
                    "module 'entity.bg.calc_data' has no attribute 'Missing'.")
    ]
    assert errors(Schedule('no_module', 'entity.missing.Task', 60))[0][0] == 'bg.E002'
    assert errors(Schedule('not_a_task', 'entity.models.ParentEntity', 60)) == [
        ('bg.E002', 'The schedule not_a_task: entity.models.ParentEntity is not a BgBase task class.')
    ]
    [(check, message)] = errors(Schedule('wrong_kwargs', LOG_MESSAGE, 60, kwargs={'text': 'm'}))
    assert check == 'bg.E002'
    assert "the kwargs do not fit the arguments of entity.bg.calc_data.LogMessage" in message

    problems = [msg for _id, msg in errors(
        Schedule('Bad Slug', LOG_MESSAGE, 'every hour', '', {'author': 1, 'message': 'm'}, enabled='yes')
    )]
    assert problems == [
        'The schedule Bad Slug: the slug \'Bad Slug\' is invalid (lowercase letters, digits, "_" and "-").',
        'The schedule Bad Slug: its name is not a text (an English gettext_lazy msgid).',
        "The schedule Bad Slug: the cron expression 'every hour' is invalid: improper number of "
        'cron entries specified; got 2 need 5 to 7.',
        'The schedule Bad Slug: the kwargs author are taken by delay() for itself.',
        'The schedule Bad Slug: enabled is not a boolean.',
        'The schedule Bad Slug: the kwargs do not fit the arguments of entity.bg.calc_data.LogMessage: '
        "got an unexpected keyword argument 'author'.",
    ]
    for period, problem in (
        (0, 'the period in seconds is not positive'),
        (True, 'the period is neither seconds nor a cron expression'),
        ('61 * * * *', "the cron expression '61 * * * *' is invalid: item value 61 out of range [0, 59]"),
    ):
        assert errors(Schedule('period', LOG_MESSAGE, period, kwargs={'message': 'm'})) == [
            ('bg.E001', f'The schedule period: {problem}.')
        ]
    assert errors(Schedule('json', LOG_MESSAGE, 60, kwargs={'message': ('a', 'b')})) == [
        ('bg.E001', 'The schedule json: the kwargs are not JSON (strings, numbers, booleans, None, '
                    'lists, dicts).')
    ]
    twice = Schedule('twice', LOG_MESSAGE, 60, kwargs={'message': 'm'})
    assert [it.id for it in declaration_messages([('a', twice), ('b', twice)])] == ['bg.E001']
    assert errors('not a schedule') == [('bg.E001', "'not a schedule' of test is not a Schedule.")]


@pytest.mark.django_db
def test_invalid_declarations_are_refused():
    with pytest.raises(ImproperlyConfigured, match='bg.E002: The schedule bad_path'):
        apply(Schedule('bad_path', 'entity.bg.calc_data.Missing', 60))
    assert not TaskCron.objects.filter(slug='bad_path').exists()


@pytest.mark.django_db
def test_the_fixture_of_the_test_utils_applies_the_schedules(bazis_declared):
    # the migrated test database already has them
    assert bazis_declared == []
    TaskCron.objects.filter(slug='entity_log_hourly').update(period='60', is_enable=False)
    assert plugin.apply_declarations() == ['taskcron entity_log_hourly: period, is_enable changed']
    cron = TaskCron.objects.get(slug='entity_log_hourly')
    assert (cron.period, cron.is_enable) == ('3600', True)


@pytest.mark.django_db
def test_the_scheduler_runs_the_declared_periodic_task():
    from bazis.contrib.bg.management.commands.bg_scheduler import Command as Scheduler

    cron = TaskCron.objects.get(slug='entity_log_hourly')
    TaskCron.objects.filter(pk=cron.pk).update(dt_run=now() - timedelta(seconds=1))
    Scheduler().cron_check()
    task = Task.objects.get(task_cron=cron)
    assert (task.cls_path, task.kwargs, task.state) == (LOG_MESSAGE, {'message': 'hourly'}, 'waiting')


@pytest.mark.django_db
def test_the_admin_keeps_declared_periodic_tasks_read_only(admin_user):
    request = RequestFactory().get('/')
    request.user = admin_user
    model_admin = TaskCronAdmin(TaskCron, AdminSite())
    declared = TaskCron.objects.get(slug='entity_log_hourly')
    ordinary = TaskCron.objects.create(name='Admin', cls_path=LOG_MESSAGE, period='60')

    readonly = model_admin.get_readonly_fields(request, declared)
    assert {'name', 'slug', 'cls_path', 'period', 'args', 'kwargs', 'is_enable', 'managed'} <= set(readonly)
    # it still runs it now (dt_run) and sets its environment
    assert not {'dt_run', 'envs'} & set(readonly)
    assert model_admin.has_change_permission(request, declared)
    assert not model_admin.has_delete_permission(request, declared)

    readonly = model_admin.get_readonly_fields(request, ordinary)
    assert 'managed' in readonly
    assert not {'name', 'slug', 'cls_path', 'period', 'kwargs', 'is_enable'} & set(readonly)
    assert model_admin.has_delete_permission(request, ordinary)
    form = model_admin.get_form(request, declared)(instance=declared)
    assert set(form.fields) == {'dt_run', 'envs'}


def delete_old_cron(apps, schema_editor):
    """
    The recipe of the guide, for the task of the sample schedule.
    """
    apps.get_model('bg', 'TaskCron').objects.filter(
        cls_path='entity.bg.calc_data.LogMessage', slug=None,
    ).delete()


@pytest.mark.django_db
@pytest.mark.parametrize('declared_applied', [True, False], ids=['declared_row_exists', 'fresh'])
def test_a_periodic_task_of_a_data_migration_runs_a_schedule_again(declared_applied):
    """
    A periodic task made by a `get_or_create` data migration (no slug) and then declared:
    the schedule creates a second one, bg.W002 reports it. The recipe of the guide (a data
    migration that deletes the old row) works whether `migrate` already created the declared
    row (a database where the schedule was applied) or not (it runs before the schedules
    are applied); the tasks of the old row are kept, unlinked.
    """
    if not declared_applied:
        TaskCron.objects.filter(slug='entity_log_hourly').delete()
    old = TaskCron.objects.create(
        name='Hourly', cls_path=LOG_MESSAGE, period='3600', kwargs={'message': 'hourly'}
    )
    old_task = LogMessage.delay('hourly')
    Task.objects.filter(pk=old_task.pk).update(task_cron=old)

    if declared_applied:
        [warning] = check_declarations_applied(None, databases=['default'])
        assert warning.id == 'bg.W002'
        assert f'taskcron {old.pk} (Hourly) runs the schedule entity_log_hourly' in warning.msg
        assert 'filter(cls_path=..., slug=None).delete()' in warning.hint
    assert declare.duplicates() == [f'taskcron {old.pk} (Hourly) runs the schedule entity_log_hourly']

    # the data migration, with the models of the migrations
    delete_old_cron(MigrationExecutor(connection).loader.project_state().apps, None)
    changes = apply_declarations()

    assert changes == ([] if declared_applied else ['taskcron entity_log_hourly: created'])
    assert list(TaskCron.objects.filter(cls_path=LOG_MESSAGE).values_list('slug', flat=True)) == [
        'entity_log_hourly'
    ]
    assert Task.objects.get(pk=old_task.pk).task_cron is None
    assert declare.duplicates() == []
    assert check_declarations_applied(None, databases=['default']) == []


@pytest.mark.django_db
def test_other_periodic_tasks_of_the_class_are_not_duplicates():
    TaskCron.objects.create(name='Other', cls_path=LOG_MESSAGE, period='60', kwargs={'message': 'x'})
    TaskCron.objects.create(
        name='Off', cls_path=LOG_MESSAGE, period='60', kwargs={'message': 'hourly'}, is_enable=False
    )
    assert declare.duplicates() == []


@pytest.mark.django_db
def test_a_periodic_task_without_kwargs_runs_a_schedule_without_kwargs_again():
    unnamed = Schedule('nightly_clean', 'bazis.contrib.bg.bg.tasks_clean.BgTasksClean', '0 3 * * *')
    cron = TaskCron.objects.create(
        name='Clean', cls_path='bazis.contrib.bg.bg.tasks_clean.BgTasksClean', period='3600'
    )
    assert declare.duplicates(schedules=[unnamed]) == [
        f'taskcron {cron.pk} (Clean) runs the schedule nightly_clean'
    ]


@pytest.mark.django_db
def test_the_changelist_locks_the_declared_periodic_tasks(admin_user):
    request = RequestFactory().get('/')
    request.user = admin_user
    model_admin = TaskCronAdmin(TaskCron, AdminSite())
    TaskCron.objects.create(name='Admin', cls_path=LOG_MESSAGE, period='60')

    formset = model_admin.get_changelist_formset(request)(queryset=TaskCron.objects.order_by('pk'))
    enabled = {form.instance.slug: form.fields['is_enable'].disabled for form in formset.forms}
    assert enabled == {'entity_log_hourly': True, None: False}
