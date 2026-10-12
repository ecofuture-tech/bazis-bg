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

from django.db import migrations


def adopt_cleanup(apps, schema_editor):
    """
    The periodic task of the cleanup made by the command `cleanup_init` (without a slug)
    becomes the one declared in `bazis.contrib.bg.schedules`, which `migrate` then updates:
    otherwise both would run the cleanup.
    """
    TaskCron = apps.get_model('bg', 'TaskCron')  # noqa: N806
    cron = (
        TaskCron.objects.using(schema_editor.connection.alias)
        .filter(cls_path='bazis.contrib.bg.bg.tasks_clean.BgTasksClean', slug=None)
        .order_by('pk')
        .first()
    )
    if cron is not None:
        cron.slug, cron.managed = 'bg_tasks_clean', True
        cron.save(update_fields=['slug', 'managed'])


class Migration(migrations.Migration):
    dependencies = [
        ('bg', '0006_taskcron_slug_managed'),
    ]

    operations = [
        migrations.RunPython(adopt_cleanup, migrations.RunPython.noop),
    ]
