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

"""
The recipe of the guide (bazis/contrib/bg/AGENTS.md) for an export for the user of a
request: the user and the language are arguments of the task, the rows are restricted by
the `restrict_queryset` of the default route, the texts are in the language of the user.
"""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import translation
from django.utils.translation import gettext_lazy as _

import pytest
from entity.bg.calc_data import LogMessage
from openpyxl import load_workbook

from bazis.contrib.bg.basic.base_download import BgBaseDownload
from bazis.contrib.bg.models import Task
from bazis.contrib.bg.routes import BgRoute
from bazis.core.schemas import CrudAccessAction


class TasksExport(BgBaseDownload):
    name = 'Tasks'
    fields_read = ['name', 'dt_created']
    file_name = 'tasks'

    def __init__(self, user_id, language):
        self.user = get_user_model().objects.get(pk=user_id)
        self.language = language

    def handle(self):
        with translation.override(self.language):
            super().handle()

    def get_titles(self):
        # a msgid of the catalog of the core
        return {'name': 'Name', 'dt_created': _('Creation time')}

    def queryset(self):
        qs = BgRoute.restrict_queryset(
            Task.objects.exclude(cls_path=self.get_path()), CrudAccessAction.VIEW, user=self.user
        )
        return qs.order_by('name')

    def get_count(self):
        return self.queryset().count()

    def get_queryset(self):
        return self.queryset()


@pytest.mark.django_db(transaction=True)
def test_export_for_the_user_of_a_request(settings, tmp_path, monkeypatch):
    from django.conf import settings as django_settings

    settings.MEDIA_ROOT = str(tmp_path)
    monkeypatch.setattr(django_settings, 'LANGUAGES', [('en', 'English'), ('ru', 'Русский')])
    user_model = get_user_model()
    user = user_model.objects.create_user('user', email='user@site.com', password='weak_password_1')
    other = user_model.objects.create_user('other', email='other@site.com', password='weak_pw_2')
    LogMessage.delay('own', name='Own task', author=user)
    LogMessage.delay('other', name='Other task', author=other)

    task = TasksExport.delay(user_id=str(user.pk), language='ru', author=user)
    call_command('bg_task', task_id=task.id)
    task.refresh_from_db()

    assert task.is_success, task.error
    # the user reads his task (and its file) through the task route
    visible = BgRoute.restrict_queryset(Task.objects.all(), CrudAccessAction.VIEW, user=user)
    assert visible.filter(pk=task.pk).exists()
    rows = list(load_workbook(task.file.path).active.values)
    assert rows[0] == ('Name', 'Время добавления')
    # only the tasks of the user
    assert [row[0] for row in rows[1:]] == ['Own task']
