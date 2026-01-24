from datetime import timedelta

from django.conf import settings
from django.utils.timezone import now

from ..basic.base import BgBase
from ..models import Task


class BgTasksClean(BgBase):
    name = 'Background tasks cleanup'
    parallel = 1

    def handle(self):
        # get all manual tasks that have not been updated for longer than the specified period
        qs = Task.objects.filter(
            dt_updated__lt=(now() - timedelta(seconds=settings.BAZIS_TASK_LIFETIME)),
            task_cron__isnull=True,
        )
        self.next_phase('Manual tasks cleanup', expected=qs.count())
        qs._raw_delete(qs.db)

        # get all periodic tasks that have not been updated for longer than the specified period
        qs = Task.objects.filter(
            dt_updated__lt=(now() - timedelta(seconds=settings.BAZIS_TASK_CRON_LIFETIME)),
            task_cron__isnull=False,
        )
        self.next_phase('Periodic tasks cleanup', expected=qs.count())
        qs._raw_delete(qs.db)
