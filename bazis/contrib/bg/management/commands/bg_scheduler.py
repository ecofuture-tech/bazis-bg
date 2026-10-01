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

import asyncio
import logging
import os
import socket
import sys
import threading
import traceback
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from time import sleep

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils.timezone import now

import aiohttp
import psutil
from asgiref.sync import sync_to_async
from crontab import CronTab

from bazis.core.utils.functools import throttle
from bazis.core.utils.network import check_port, healthcheck_server


sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

LOG = logging.getLogger(__name__)


def cron_next_run(period: str) -> datetime:
    """
    Returns the next run time of a cron expression (evaluated in UTC) as an aware datetime.
    """
    return datetime.fromtimestamp(CronTab(period).next(default_utc=True, delta=False), tz=UTC)


def proc_start(cmd, envs=None):
    env = os.environ.copy()
    env.update(envs or {})
    return psutil.Popen([str(x) for x in cmd], env=env)


class Command(BaseCommand):
    #: the number of waiting tasks examined in one cycle
    prepare_batch = 100

    @staticmethod
    def _task_cron_update(task_cron, **kwargs):
        for k, v in kwargs.items():
            setattr(task_cron, k, v)
        task_cron.save(update_fields=kwargs.keys())

    @throttle(5)
    def cron_check(self):
        TaskCron = apps.get_model('bg.TaskCron') # noqa F806
        Task = apps.get_model('bg.Task') # noqa F806

        # iterate over all cron tasks
        for task_cron in TaskCron.objects.filter(is_enable=True).annotate(
            is_task_executing=Exists(
                Task.objects.filter(
                    Q(
                        task_cron=OuterRef('pk'),
                    )
                    & ~Q(state='done')
                ).values('id')
            ),
            task_dt_finish=Subquery(
                Task.objects.filter(
                    Q(
                        task_cron=OuterRef('pk'),
                    )
                    & Q(state='done')
                )
                .order_by('-dt_finish')
                .values('dt_finish')[:1]
            ),
        ):
            task_cls = task_cron.cls
            if not task_cls:
                LOG.warning('Cron task class not found: %s', task_cron.cls_path)
                continue

            # if the next run time is specified - check it
            if task_cron.dt_run:
                if task_cron.dt_run <= now():
                    # create a specific task
                    kwargs = dict(
                        task_cron.kwargs or {},
                        **{
                            'envs': task_cron.envs,
                        },
                    )
                    # actually start the task, preserving the original cron task
                    task = task_cls.delay(*(task_cron.args or []), **kwargs)
                    task.task_cron = task_cron
                    task.save(update_fields=['task_cron'])

                    # reset the next run time
                    self._task_cron_update(task_cron, dt_run=None)
                # in any case - no more checks are needed in this iteration
                continue

            # if it is assumed that the run will be periodic
            if task_cron.period.isnumeric():
                # then the period is specified in seconds
                seconds = float(task_cron.period)
                # if the task is currently running - no new run is required
                if task_cron.is_task_executing:
                    continue
                # get the last completed task
                # set the next run time, counting from the completion time of the previous task
                self._task_cron_update(
                    task_cron,
                    dt_run=(task_cron.task_dt_finish or now()) + timedelta(seconds=seconds)
                )
            else:
                # try to create a cron object
                try:
                    dt_run = cron_next_run(task_cron.period)
                except Exception:  # NOQA [B902]
                    # in case of an error, write it to the task
                    self._task_cron_update(task_cron, error=traceback.format_exc())
                else:
                    # write the time of the next run to the task (fromtimestamp without tz
                    # used the time zone of the server instead of UTC)
                    self._task_cron_update(task_cron, dt_run=dt_run)

    @throttle(2)
    def tasks_check(self):
        Task = apps.get_model('bg.Task') # noqa F806

        # explicitly disable all tasks in the DB that are linked to handlers missing from the table
        Task.objects.filter(
            Q(state='running') | Q(state='done', dt_finish=None), Q(handler=None)
        ).update(
            phase='Unhandled interruption',
            error='The task was interrupted for an unknown reason',
            state='done',
            dt_finish=now(),
        )

    @staticmethod
    def _reject_phase(task_cls, actives_cls) -> str | None:
        """
        The reason why no more tasks of the class can start now, or None.
        """
        if len(actives_cls[task_cls.get_path()]) >= task_cls.parallel:
            return f'Maximum of {task_cls.parallel} similar tasks'
        blocked = [cls_block for cls_block in task_cls.blocked if actives_cls[cls_block]]
        if blocked:
            return 'Waiting for completion of tasks: {}'.format(', '.join(blocked))
        return None

    def tasks_prepare(self):
        Task = apps.get_model('bg.Task') # noqa F806

        # collect all running tasks according to the DB (their number is limited by the
        # handlers): a partial list allowed more parallel tasks than permitted
        actives_cls = defaultdict(list)
        for t in Task.objects.filter(state__in=['running', 'starting']).only(
            'id', 'cls_path', 'args', 'kwargs'
        ):
            actives_cls[t.cls_path].append(t)

        with transaction.atomic():
            # interrupted waiting tasks are closed whatever their class
            for task in Task.objects.select_for_update(skip_locked=True).filter(
                state='waiting', interrupt=True
            ):
                task.set_done('interrupted')

            # the classes that cannot start a task now are excluded from the query below:
            # otherwise their waiting tasks could fill the batch and the tasks of the other
            # classes never started
            startable = []
            for cls_path in (
                Task.objects.filter(state='waiting').values_list('cls_path', flat=True).distinct()
            ):
                task_cls = Task(cls_path=cls_path).cls
                if not task_cls:
                    Task.objects.filter(state='waiting', cls_path=cls_path).delete()
                    continue
                if phase_reject := self._reject_phase(task_cls, actives_cls):
                    Task.objects.filter(state='waiting', cls_path=cls_path).exclude(
                        phase=phase_reject
                    ).update(phase=phase_reject)
                    continue
                startable.append(cls_path)

            # the oldest waiting tasks of these classes start first
            for task in (
                Task.objects.select_for_update(skip_locked=True)
                .filter(state='waiting', cls_path__in=startable)
                .order_by('dt_created')[: self.prepare_batch]
            ):
                if any(
                    t.args == task.args and t.kwargs == task.kwargs
                    for t in actives_cls[task.cls_path]
                ):
                    phase_reject = 'The task is already running. Waiting for completion'
                else:
                    # the limits change as tasks of this batch start
                    phase_reject = self._reject_phase(task.cls, actives_cls)

                if phase_reject:
                    # update the status only if it has been changed
                    if task.phase != phase_reject:
                        task.phase = phase_reject
                        task.save(update_fields=['phase'])
                    continue

                # mark the task for launch
                task.state = 'starting'
                task.save(update_fields=['state'])

                actives_cls[task.cls_path].append(task)

    def start_handlers_check(self):
        TaskHandler = apps.get_model('bg.TaskHandler') # noqa F806

        async def main_thread_loop_work():
            while True:
                handlers = [handler async for handler in TaskHandler.objects.all()]

                async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                    items = [
                        session.get(f'http://{handler.host}:{handler.port}/pid')
                        for handler in handlers
                    ]
                    results = await asyncio.gather(*items, return_exceptions=True)

                for_delete = [
                    handlers[i].pk
                    for i, r in enumerate(results)
                    if isinstance(r, Exception)
                    or r.status != 200
                    or (await r.text()) != handlers[i].pid
                ]

                await sync_to_async(TaskHandler.objects.filter(pk__in=for_delete).delete)()

                await asyncio.sleep(3)

        def thead_worker():
            asyncio.run(main_thread_loop_work())

        # start a separate thread to poll handlers
        th = threading.Thread(target=thead_worker, daemon=True)
        th.start()

    @throttle(30)
    def run_handlers(self):
        TaskHandler = apps.get_model('bg.TaskHandler') # noqa F806

        ports_inuse = set(TaskHandler.objects.values_list('port', flat=True))

        for _ in range(settings.BAZIS_TASK_HANDLERS_LOCAL - len(ports_inuse)):
            for i in range(1000):
                port = settings.BAZIS_TASK_HANDLER_PORT + i
                if port not in ports_inuse:
                    if check_port(port):
                        LOG.info(f'Handler localhost:{port} has been ran')
                        proc_start(
                            [
                                sys.executable,
                                'manage.py',
                                'bg_handler',
                                '--host',
                                '127.0.0.1',
                                '--port',
                                port,
                            ]
                        )
                        ports_inuse.add(port)
                        break

    def handle(self, **kwargs):
        LOG.info('Bazis BG Scheduler started')

        healthcheck_server(
            settings.BAZIS_TASK_SCHEDULER_HOST or socket.gethostname(),
            settings.BAZIS_TASK_SCHEDULER_PORT,
        )
        LOG.info(
            f'Healthcheck server started at {settings.BAZIS_TASK_SCHEDULER_HOST or socket.gethostname()}:{settings.BAZIS_TASK_SCHEDULER_PORT}'
        )

        self.start_handlers_check()

        LOG.info('Entering main loop')

        while True:
            self.run_handlers()

            # perform cron tasks check
            self.cron_check()

            # perform tasks check
            self.tasks_check()

            # perform process start
            self.tasks_prepare()

            # delay
            sleep(settings.BAZIS_TASK_SCHEDULER_IDLE)
