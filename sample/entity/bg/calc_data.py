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

from django.utils.translation import gettext_lazy as _

from bazis.contrib.bg.basic.base import BgBase
from bazis.contrib.bg.basic.base_download_model import BgBaseDownloadModel

from entity.models import ParentEntity


class CalcData(BgBase):
    name = _('Calc data')
    parallel = 1

    def handle(self) -> None:
        qs = ParentEntity.objects.all()
        self.next_phase(phase_name='First phase: parents', expected=qs.count())

        for parent in ParentEntity.objects.all():
            parent.is_active = True
            parent.save()
            self.progress()


class LogMessage(BgBase):
    """
    Logs its argument: used by the tests of the task logs.
    """

    name = _('Log message')
    parallel = 2

    def handle(self) -> None:
        self.log.info('message: %s', self.message)

    def __init__(self, message: str):
        self.message = message


class ExportParents(BgBaseDownloadModel):
    """
    Exports the parent entities: used by the tests of the export.
    """

    model = ParentEntity
    fields_read = ['name', 'is_active', 'price']
