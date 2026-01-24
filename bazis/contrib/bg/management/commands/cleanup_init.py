from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.translation import gettext_lazy as _


class Command(BaseCommand):
    help = _('Initialize cleanup cron task')

    def handle(self, *args, **options):
        TaskCron = apps.get_model('bg.TaskCron') # noqa F806

        TaskCron.objects.get_or_create(
            cls_path='bazis.contrib.bg.bg.tasks_clean.BgTasksClean',
            defaults=dict(
                name=_('Clean tasks'),
                period=settings.BAZIS_TASK_CRON_CLEANUP,
            ),
        )
