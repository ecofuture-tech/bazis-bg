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

from django.core.exceptions import FieldDoesNotExist

from ..basic.base_download import BgBaseDownload


class BgBaseDownloadModel(BgBaseDownload):
    model = None

    @classmethod
    def get_name(cls):
        return f'Export: {cls.model._meta.verbose_name}'

    def get_titles(self):
        fields = {}
        for k in self.fields_read:
            try:
                fields[k] = self.model._meta.get_field(k).verbose_name
            except FieldDoesNotExist:
                fields[k] = k
        return fields

    def __init__(self):
        self.qs = self.model.objects.all()
        self.file_name = self.model.get_resource_name()

    def get_queryset(self):
        return self.qs

    def get_count(self):
        return self.qs.count()
