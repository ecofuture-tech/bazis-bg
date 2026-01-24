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
