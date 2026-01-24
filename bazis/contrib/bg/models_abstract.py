from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.db import models
from django.utils.functional import cached_property
from django.utils.timezone import now

from bazis.contrib.author.models_abstract import AuthorMixin
from bazis.core.models_abstract import DtMixin, InitialBase, UuidMixin
from bazis.core.utils.imp import import_class
from bazis.core.utils.orm import JsonFieldEncoder


def task_file_name(obj, fn):
    return f'{settings.BAZIS_TASK_FOLDER}/{fn}'


if settings.BAZIS_STORAGE_BG:
    TaskStorage = import_class(settings.BAZIS_STORAGE_BG)
else:
    TaskStorage = FileSystemStorage


class TaskBaseModel(UuidMixin, DtMixin, AuthorMixin):
    name = models.CharField('Name', max_length=255)
    cls_path = models.CharField('Task class', max_length=255, db_index=True)
    args = models.JSONField(null=True, blank=True)
    kwargs = models.JSONField(null=True, blank=True)
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
        'File', upload_to=task_file_name, blank=True, null=True
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._meta.get_field('file').storage = TaskStorage()

    class Meta:
        abstract = True
        verbose_name = 'Background task'
        verbose_name_plural = 'Background tasks'
        ordering = ['-id']
        index_together = [
            ('cls_path', 'state'),
            ('state', 'dt_finish'),
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
