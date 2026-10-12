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
The actions of `LoadDownloadAdminMixin`: its change list gives `file_load.js` the actions
that load a file, the message of a started task escapes its name. The other change lists,
the tasks and periodic tasks of bazis-bg too, are those of Django.
"""

from django.contrib import admin
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

import pytest
from entity.bg.calc_data import CalcData
from entity.models import ParentEntity

from bazis.contrib.bg.admin_abstract import LoadDownloadAdminMixin
from bazis.contrib.bg.basic.base import BgBase


class MarkedTask(BgBase):
    name = '<b>Marked</b>'


class ParentTasksAdmin(LoadDownloadAdminMixin, admin.ModelAdmin):
    tasks_load = [CalcData]
    tasks_handler = [MarkedTask]


def request_of(user, method='get'):
    request = getattr(RequestFactory(), method)('/')
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.django_db
def test_the_change_list_gives_the_load_actions(admin_user):
    model_admin = ParentTasksAdmin(ParentEntity, admin.site)
    content = model_admin.changelist_view(request_of(admin_user)).render().content.decode()

    assert (
        '<script id="bg-actions-task-load" type="application/json">["action_calcdata"]</script>'
        in content
    )
    assert 'admin/js/file_load.js' in content
    assert 'jquery-3.5.1' not in content


@pytest.mark.django_db
def test_the_message_of_a_started_task_escapes_its_name(admin_user):
    request = request_of(admin_user, 'post')
    model_admin = ParentTasksAdmin(ParentEntity, admin.site)

    model_admin.action_markedtask(request, ParentEntity.objects.none())

    [message] = get_messages(request)
    assert str(message).startswith('Started: <a href="/admin/bg/task/')
    assert str(message).endswith('target="_blank">&lt;b&gt;Marked&lt;/b&gt;</a>')


@pytest.mark.django_db
@pytest.mark.parametrize(
    'url', ['/admin/entity/parententity/', '/admin/bg/task/', '/admin/bg/taskcron/']
)
def test_other_change_lists_are_those_of_django(admin_client, url):
    """
    The template of the mixin is not one Django looks up for the models of an application
    (`admin/<app>/change_list.html`): the admin of the tasks does not get it either.
    """
    response = admin_client.get(url)
    assert response.status_code == 200
    assert 'bg-actions-task-load' not in response.content.decode()
