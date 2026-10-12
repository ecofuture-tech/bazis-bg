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

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """
    Deprecated, does nothing: the cleanup is the periodic task `bg_tasks_clean` declared by
    bazis-bg (`bazis.contrib.bg.schedules`), which `migrate` applies. Kept so that the deploy
    scripts that call it do not fail; removed in bazis-bg 2.7.
    """

    help = 'Deprecated, does nothing: migrate applies the cleanup periodic task'

    def handle(self, *args, **options):
        self.stderr.write(
            'cleanup_init is deprecated and does nothing: migrate applies the periodic task '
            'bg_tasks_clean of bazis-bg. Remove the call; the command is removed in bazis-bg 2.7.'
        )
