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

import os
import re
import secrets

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now

from bazis.contrib.author.models_abstract import AuthorMixin
from bazis.core.models_abstract import DtMixin, InitialBase, UuidMixin
from bazis.core.utils.imp import import_class
from bazis.core.utils.orm import JsonFieldEncoder


#: the stored name of a task file: a random token (the url-safe base64 of 16 bytes, 22
#: characters), `_` and the name of the file. Not a dot: the storage shortens a name too
#: long for the field in the part before its first dot
TASK_FILE_TOKEN = re.compile(r'^[A-Za-z0-9_-]{22}_(?P<name>.+)$')


def task_file_name(obj, fn):
    """
    The stored name of a task file: `<BAZIS_TASK_FOLDER>/<token>_<name>`. The random token
    keeps the file from being guessed on the media host, which serves it without a check:
    an export holds personal data. The API serves it to the author of the task and staff
    (`BgRoute.action_download`).
    """
    return f'{settings.BAZIS_TASK_FOLDER}/{secrets.token_urlsafe(16)}_{os.path.basename(fn)}'


def task_file_download_name(name: str) -> str:
    """
    The name of a stored task file without its folder and token (`task_file_name`); a file
    stored before the token (bazis-bg 2.5) keeps its name.
    """
    name = os.path.basename(name)
    match = TASK_FILE_TOKEN.match(name)
    return match['name'] if match else name


#: the last line of a traceback: the class of the exception (with its module), then its
#: message, if any
TRACEBACK_EXCEPTION = re.compile(r'^(?:[A-Za-z_]\w*\.)*(?P<name>[A-Za-z_]\w*)(?::|$)')


def task_error_summary(error: str | None) -> str | None:
    """
    The error of a task for its author: the class of the exception of the traceback
    (`ValueError`), `Error` for a text that is not a traceback; no error stays as it is. The
    traceback and its message hold paths, code and data of the server (a database error
    quotes the row).
    """
    if not error:
        return error
    lines = error.strip().splitlines()
    match = TRACEBACK_EXCEPTION.match(lines[-1]) if error.startswith('Traceback') else None
    return match['name'] if match else 'Error'


if settings.BAZIS_STORAGE_BG:
    TaskStorage = import_class(settings.BAZIS_STORAGE_BG)
else:
    TaskStorage = FileSystemStorage


def get_task_storage():
    """
    Returns the storage of the task files: the class from BAZIS_STORAGE_BG, or the file
    system storage in MEDIA_ROOT.
    """
    return TaskStorage()


class TaskBaseModel(UuidMixin, DtMixin, AuthorMixin):
    name = models.CharField('Name', max_length=255)
    cls_path = models.CharField('Task class', max_length=255, db_index=True)
    args = models.JSONField(null=True, blank=True)
    kwargs = models.JSONField(null=True, blank=True)
    #: stored with the task, not applied to the process that runs it. Kept while products
    #: write it (their data migrations and tests set `envs`); removed with the migration that
    #: removes `Task.pid`, which is never filled either
    envs = models.JSONField(null=True, blank=True)
    error = models.TextField('Error', null=True, blank=True)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name

    @cached_property
    def cls(self):
        try:
            return import_class(self.cls_path)
        except Exception:
            return


class TaskBase(TaskBaseModel):
    STATES = [
        ('draft', 'Draft'),
        ('waiting', 'Waiting'),
        ('starting', 'Starting'),
        ('running', 'Running'),
        ('done', 'Completed'),
    ]
    pid = models.CharField('PID', max_length=36, db_index=True)
    handler = models.ForeignKey('TaskHandler', blank=True, null=True, on_delete=models.SET_NULL)
    state = models.CharField(
        'State', max_length=35, choices=STATES, default=STATES[0][0], db_index=True
    )
    phase = models.CharField('Phase', max_length=1024)
    phases_history = models.JSONField('History', encoder=JsonFieldEncoder, null=True, blank=True)
    interrupt = models.BooleanField('Interrupted manually', default=False, db_index=True)
    dt_start = models.DateTimeField('Start time', null=True, blank=True, db_index=True)
    dt_finish = models.DateTimeField('Finish time', null=True, blank=True, db_index=True)
    file = models.FileField(
        'File', upload_to=task_file_name, blank=True, null=True, storage=get_task_storage
    )
    file_params = models.JSONField(null=True, encoder=JsonFieldEncoder, blank=True)
    log = models.TextField('Log', blank=True, null=True)
    expected = models.JSONField('Expected', encoder=JsonFieldEncoder, null=True, blank=True)
    performed = models.JSONField('Performed', encoder=JsonFieldEncoder, null=True, blank=True)
    task_cron = models.ForeignKey(
        'TaskCron',
        verbose_name='Periodic task',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    result = models.JSONField('Result', encoder=JsonFieldEncoder, null=True, blank=True)

    class Meta:
        abstract = True
        verbose_name = 'Background task'
        verbose_name_plural = 'Background tasks'
        ordering = ['-id']
        indexes = [
            models.Index(fields=['cls_path', 'state'], name='%(app_label)s_%(class)s_cls_state'),
            models.Index(fields=['state', 'dt_finish'], name='%(app_label)s_%(class)s_state_fin'),
        ]

    def set_done(self, phase, error=None):
        self.dt_finish = now()
        self.error = error
        self.phase = phase
        self.state = 'done'
        self.save(update_fields=['state', 'phase', 'error', 'dt_finish'])

    @property
    def is_done(self):
        return self.state == 'done'

    @property
    def is_success(self):
        return (self.state == 'done') and (not self.error) and (not self.interrupt)

    @property
    def is_error(self):
        return (self.state == 'done') and self.error

    @property
    def is_interrupt(self):
        return (self.state == 'done') and self.interrupt


class TaskCronBase(TaskBaseModel):
    period = models.CharField('Period value', max_length=100)
    dt_run = models.DateTimeField('Next run time', null=True, blank=True)
    is_enable = models.BooleanField('Enabled', default=True, db_index=True)
    #: the slug of a schedule declared in a `schedules.py` module (bazis.contrib.bg.declare)
    slug = models.CharField('Slug', max_length=255, unique=True, null=True, blank=True)
    #: declared in a `schedules.py` module of an application: `migrate` keeps it as
    #: declared, the admin does not change it
    managed = models.BooleanField('Managed by the code', default=False, editable=False)

    class Meta:
        abstract = True
        verbose_name = 'Periodic task'
        verbose_name_plural = 'Periodic tasks'


class TaskHandlerBase(UuidMixin, InitialBase):
    class Meta:
        abstract = True
        verbose_name = 'Handler'
        verbose_name_plural = 'Handlers'

    pid = models.CharField('PID', max_length=255, unique=True)
    host = models.CharField('Host', max_length=255)
    port = models.PositiveIntegerField('Port')
