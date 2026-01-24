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
import socket
import sys
import traceback
from random import randint
from time import sleep, time

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.timezone import now

from aiohttp import web

from bazis.core.utils.functools import throttle
from bazis.core.utils.network import healthcheck_server


sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)


LOG = logging.getLogger(__name__)


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--host', default=None, type=str)
        parser.add_argument('--port', default=None, type=int)

    def handle(self, host=None, port=None, **kwargs):
        TaskHandler = apps.get_model('bg.TaskHandler') # noqa F806
        Task = apps.get_model('bg.Task') # noqa F806

        host = host or settings.BAZIS_TASK_SCHEDULER_HOST or socket.gethostname()
        port = port or settings.BAZIS_TASK_HANDLER_PORT
        pid = f'{host}-{os.getpid()}'
        time_start = time()

        async def get_pid(r):
            return web.Response(text=pid)

        try:
            healthcheck_server(host, port, pid=get_pid)
        except Exception as e:
            LOG.error(str(e))
            return

        @throttle(5)
        def stop_check():
            return not TaskHandler.objects.filter(pid=pid).exists()

        @throttle(randint(3600 * 2, 3600 * 4), first_run=False)
        def stop_loop():
            return True

        # when starting, the handler is registered in the handlers table
        handler = TaskHandler.objects.create(
            pid=f'{pid}',
            host=host,
            port=port,
        )

        while not stop_check():

            if stop_loop():
                LOG.info(
                    f'Shutting down handler by time {pid}. Worked: {time() - time_start} sec'
                )
                break

            with transaction.atomic():
                for task in Task.objects.select_for_update(skip_locked=True).filter(
                    state='starting'
                )[:1]:
                    task.handler = handler
                    task.state = 'running'
                    task.phase = 'started'
                    task.dt_start = now()
                    task.save()
                    break
                else:
                    # delay
                    sleep(settings.BAZIS_TASK_HANDLER_IDLE)
                    continue

            # TODO: set ENVS
            LOG.info(f'Starting task {task.id} ({task.name})...')

            try:
                task.cls.run(task, *task.args, **task.kwargs)
            except Exception:  # NOQA [B902]
                task.set_done('Startup error', traceback.format_exc())
                LOG.error(task.error)
            else:
                if task := Task.objects.filter(id=task.id).first():
                    if task.state != 'done':
                        err = 'Uncaught execution error'
                        task.set_done(err, error=err)
                        LOG.error(f'Task {task.id}: {err}')
                    else:
                        LOG.info(f'Task {task.id} ({task.name}) completed successfully.')
