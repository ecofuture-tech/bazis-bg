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

import tempfile

from django.core.management import call_command
from django.db import transaction

from bazis.contrib.bg.basic.base import BgBase


class FixtureLoad(BgBase):
    name = 'Fixture loading'
    parallel = 1
    clear_models = []

    def handle(self):
        with transaction.atomic():
            # clear models
            for model in self.clear_models:
                model.objects.all().delete()

            # get file
            fp = self.task_file_get()

            # create a temporary local file, since the file may be taken from S3
            tmp_fp = tempfile.NamedTemporaryFile(suffix='.json')
            tmp_fp.write(fp.read())
            tmp_fp.seek(0)

            try:
                call_command('loaddata', tmp_fp.name, ignorenonexistent=True)
            finally:
                tmp_fp.close()
