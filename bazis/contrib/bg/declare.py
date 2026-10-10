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
The periodic tasks declared in the code of the applications.

An application declares them in `<app>/schedules.py`::

    from django.utils.translation import gettext_lazy as _
    from bazis.contrib.bg.declare import Schedule

    SCHEDULES = [
        Schedule('deadlines_remind', 'training.bg.deadlines.RemindDeadlines', '0 6 * * *',
                 _('Deadline reminders'), kwargs={'days': 3}),
    ]

After `migrate` (the `post_migrate` signal, once the migrations of the project are all
applied) the database has them, in one transaction: a periodic task (`TaskCron`) of each
slug is created or updated as declared and marked `managed`; a change of its period or of
`enabled` resets its next run time (the scheduler computes it again). An existing periodic
task of the slug that is not managed (made in the admin) is taken over with a warning. A
managed periodic task no longer declared is disabled and becomes an ordinary one (not
managed): unlike the roles and transits, which stay managed with a warning, a periodic
task would otherwise keep running, and the admin may enable it again; it is not deleted,
its tasks reference it. The periodic tasks that are not declared are left as they are; an
enabled one of the same task and kwargs as a schedule (made by a `get_or_create` data
migration before the schedule) would run twice, `duplicates` lists them (bg.W002). The
name is a single column: the declared name is stored translated into the language of the
project (`LANGUAGE_CODE`).

The helpers are those of the core (`bazis.core.declare`), shared with the roles of
bazis-permit and the workflows of bazis-statusy.
"""

import inspect
import json
import re
from dataclasses import dataclass, field

from django.apps import apps
from django.conf import settings
from django.core.checks import CheckMessage, Error
from django.core.exceptions import ImproperlyConfigured
from django.db import DEFAULT_DB_ALIAS, transaction
from django.utils import translation
from django.utils.functional import Promise

from crontab import CronTab

from bazis.core.declare import ManagedSync, apply_after_migrate, discover, lock, managed_orphans
from bazis.core.utils.imp import import_class


#: the slug of a declared schedule
SLUG = re.compile(r'^[a-z0-9_-]+$')
#: the keyword arguments `delay()` takes for itself
RESERVED_KWARGS = {'name', 'fp', 'author', 'envs'}
#: the fields of a periodic task that reset its next run time when they change
RESCHEDULE = {'period', 'is_enable'}


@dataclass(frozen=True)
class Schedule:
    """
    A periodic task: its slug, its task class (`module.Class` of a `BgBase`, or the class),
    its period (seconds after the previous run finished, `3600` or `'3600'`, or a cron
    expression in UTC, `'0 3 * * *'`), its name (`gettext_lazy`; the name of the task class
    without it), the keyword arguments of the task (JSON) and whether it is enabled.
    """

    slug: str
    task: str
    period: int | str
    name: str | Promise | None = None
    kwargs: dict = field(default_factory=dict)
    enabled: bool = True

    def __post_init__(self):
        if isinstance(self.task, type) and hasattr(self.task, 'get_path'):
            object.__setattr__(self, 'task', self.task.get_path())


def declarations() -> list[tuple[str, Schedule]]:
    """
    The schedules (SCHEDULES) of the `schedules.py` modules of the applications, with their
    module.
    """
    return discover('schedules', 'SCHEDULES')


def declared_slugs() -> set[str]:
    """
    The declared slugs of the periodic tasks.
    """
    return {it.slug for _module, it in declarations() if isinstance(it, Schedule)}


def period_problem(period) -> str | None:
    """
    What is wrong with the period of a schedule, or None.
    """
    if isinstance(period, bool) or not isinstance(period, int | str):
        return 'the period is neither seconds nor a cron expression'
    period = str(period)
    if period.isnumeric():
        return None if int(period) > 0 else 'the period in seconds is not positive'
    if len(period) > 100:
        return 'the period is longer than 100 characters'
    try:
        CronTab(period)
    except ValueError as e:
        return f'the cron expression {period!r} is invalid: {e}'
    return None


def task_problem(schedule: Schedule) -> str | None:
    """
    What is wrong with the task class of a schedule and its arguments, or None.
    """
    from .basic.base import BgBase

    try:
        task_cls = import_class(schedule.task)
    except Exception as e:  # noqa: BLE001  any error of the import is the problem
        return f'the task {schedule.task!r} does not import: {e}'
    if not (isinstance(task_cls, type) and issubclass(task_cls, BgBase)):
        return f'{schedule.task} is not a BgBase task class'
    if not task_cls.get_name():
        return f'the task class {schedule.task} has no name: it cannot be queued'
    if not isinstance(schedule.kwargs, dict):
        return None
    try:
        inspect.signature(task_cls).bind(**schedule.kwargs)
    except TypeError as e:
        return f'the kwargs do not fit the arguments of {schedule.task}: {e}'
    return None


def _kwargs_problem(kwargs) -> str | None:
    if not isinstance(kwargs, dict):
        return 'the kwargs are not a dict'
    if reserved := sorted(RESERVED_KWARGS & set(kwargs)):
        return f'the kwargs {", ".join(reserved)} are taken by delay() for itself'
    try:
        if json.loads(json.dumps(kwargs)) == kwargs:
            return None
    except (TypeError, ValueError):
        pass
    return 'the kwargs are not JSON (strings, numbers, booleans, None, lists, dicts)'


def _schedule_problems(it: Schedule) -> list[str]:
    problems = []
    if not isinstance(it.slug, str) or not SLUG.match(it.slug):
        problems.append(f'the slug {it.slug!r} is invalid (lowercase letters, digits, "_" and "-")')
    if it.name is not None and not (isinstance(it.name, str | Promise) and str(it.name)):
        problems.append('its name is not a text (an English gettext_lazy msgid)')
    if problem := period_problem(it.period):
        problems.append(problem)
    if problem := _kwargs_problem(it.kwargs):
        problems.append(problem)
    if not isinstance(it.enabled, bool):
        problems.append('enabled is not a boolean')
    return problems


def declaration_messages(schedules: list[tuple[str, Schedule]]) -> list[CheckMessage]:
    """
    The problems of the declarations (the system checks bg.E001 and bg.E002);
    `apply_declarations` refuses declarations with errors.
    """
    messages = []
    modules = {}
    for module, it in schedules:
        if not isinstance(it, Schedule):
            messages.append(Error(f'{it!r} of {module} is not a Schedule.', obj=module, id='bg.E001'))
            continue
        modules.setdefault(it.slug, []).append(module)
        messages.extend(
            Error(f'The schedule {it.slug}: {problem}.', obj=module, id='bg.E001')
            for problem in _schedule_problems(it)
        )
        if problem := task_problem(it):
            messages.append(Error(f'The schedule {it.slug}: {problem}.', obj=module, id='bg.E002'))
    messages.extend(
        Error(f'The schedule {slug} is declared more than once.', obj=', '.join(found), id='bg.E001')
        for slug, found in modules.items()
        if len(found) > 1
    )
    return messages


def _values(schedule: Schedule) -> dict:
    """
    The fields of the periodic task of a schedule.
    """
    name = schedule.name or import_class(schedule.task).get_name()
    with translation.override(settings.LANGUAGE_CODE):
        name = str(name)
    return {
        'name': name,
        'cls_path': schedule.task,
        'period': str(schedule.period),
        'args': None,
        'kwargs': dict(schedule.kwargs),
        'is_enable': schedule.enabled,
    }


def apply_declarations(using: str = DEFAULT_DB_ALIAS, schedules=None, dry_run: bool = False) -> list[str]:
    """
    Applies the declared schedules (by default those of the `schedules.py` modules) to the
    database in one transaction and returns the changes; with `dry_run` only returns them.
    Applied again, it writes nothing.
    """
    if schedules is None:
        schedules = declarations()
    schedules = [it if isinstance(it, tuple) else ('', it) for it in schedules]
    if errors := [it for it in declaration_messages(schedules) if it.is_serious()]:
        raise ImproperlyConfigured(
            'Invalid declarations of schedules:\n' + '\n'.join(f'{it.id}: {it.msg}' for it in errors)
        )

    model = apps.get_model('bg.TaskCron')
    sync = ManagedSync(using, dry_run)
    with transaction.atomic(using=using):
        if not dry_run:
            # concurrent migrate runs apply them one after the other
            lock(using)
        for _module, schedule in schedules:
            obj, changed = sync.object(model, schedule.slug, _values(schedule))
            if not dry_run and obj.dt_run is not None and RESCHEDULE & set(changed):
                obj.dt_run = None
                obj.save(using=using, update_fields=['dt_run'])

        for obj in managed_orphans(model, [it.slug for _module, it in schedules], using):
            sync.changes.append(f'taskcron {obj.slug}: disabled, no longer declared')
            if not dry_run:
                obj.is_enable = obj.managed = False
                obj.save(using=using, update_fields=['is_enable', 'managed'])
    return sync.changes


def duplicates(using: str = DEFAULT_DB_ALIAS, schedules=None) -> list[str]:
    """
    The enabled periodic tasks that are not managed and run the task of a declared schedule
    with its kwargs under another slug (or none): with the declared one they run twice.
    """
    if schedules is None:
        schedules = declarations()
    schedules = [it[1] if isinstance(it, tuple) else it for it in schedules]
    model = apps.get_model('bg.TaskCron')
    candidates = model.objects.using(using).filter(
        managed=False, is_enable=True, cls_path__in=[it.task for it in schedules]
    ).order_by('pk')
    found = []
    for schedule in schedules:
        found.extend(
            f'taskcron {obj.pk} ({obj.name}) runs the schedule {schedule.slug}'
            for obj in candidates
            if obj.cls_path == schedule.task
            and obj.slug != schedule.slug
            and (obj.kwargs or {}) == schedule.kwargs
        )
    return found


def post_migrate_apply(sender, using=DEFAULT_DB_ALIAS, verbosity=1, **kwargs):
    """
    The receiver of `post_migrate` (also sent by `flush`): applies the declarations once
    the migrations of the project are all applied.
    """
    apply_after_migrate(
        apply_declarations, 'bg.TaskCron', 'schedules', using, verbosity, kwargs.get('stdout')
    )
