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

import pytest
from bazis_test_utils.utils import get_api_client
from entity.bg.calc_data import LogMessage

from bazis.contrib.bg.models import Task
from bazis.contrib.users import get_user_model
from bazis.core.introspect import validate_manifest


User = get_user_model()


def test_manifest_is_valid():
    assert validate_manifest('bazis.contrib.bg') == []


@pytest.mark.django_db(transaction=True)
def test_tasks_are_private(sample_app):
    """
    The task route listed every task, with its arguments and log, to any client.
    """
    owner = User.objects.create_user('owner', password='weak_password_1')
    stranger = User.objects.create_user('stranger', password='weak_password_2')
    staff = User.objects.create_user('staff', password='weak_password_3', is_staff=True)
    own = LogMessage.delay('own')
    Task.objects.filter(pk=own.pk).update(author=owner)
    system = LogMessage.delay('system')

    def listed(user):
        client = get_api_client(sample_app, user.jwt_build()) if user else get_api_client(sample_app)
        response = client.get('/api/v1/bg/task/')
        if response.status_code != 200:
            return response.status_code
        return {it['id'] for it in response.json()['data']}

    assert listed(None) == 401
    assert listed(owner) == {str(own.pk)}
    assert listed(stranger) == set()
    assert listed(staff) == {str(own.pk), str(system.pk)}

    response = get_api_client(sample_app, stranger.jwt_build()).get(f'/api/v1/bg/task/{own.pk}/')
    assert response.status_code == 404


REPORTS = '/api/v1/entity/report/'


def report_body(task=None, report_id=None):
    data = {'type': 'entity.report', 'attributes': {'title': 'Report'}}
    if report_id is not None:
        data['id'] = str(report_id)
    if task is not None:
        data['relationships'] = {'task': {'data': {'type': 'bg.task', 'id': str(task.pk)}}}
    return {'data': data}


@pytest.mark.django_db(transaction=True)
def test_other_routes_link_and_include_only_visible_tasks(sample_app):
    """
    Another route (the reports) links and includes only the tasks the user can see:
    `restrict_queryset` of the task route restricts them (staff see all).
    """
    owner = User.objects.create_user('owner', password='weak_password_1')
    stranger = User.objects.create_user('stranger', password='weak_password_2')
    staff = User.objects.create_user('staff', password='weak_password_3', is_staff=True)
    own = LogMessage.delay('own')
    Task.objects.filter(pk=own.pk).update(author=owner)
    owner_client = get_api_client(sample_app, owner.jwt_build())
    stranger_client = get_api_client(sample_app, stranger.jwt_build())

    response = stranger_client.post(REPORTS, json_data=report_body(own))
    assert response.status_code == 403, response.text
    error = response.json()['errors'][0]
    assert error['code'] == 'ERR_RELATION_ACCESS'
    assert error['source']['pointer'] == '/data/relationships/task'

    response = owner_client.post(REPORTS, json_data=report_body(own))
    assert response.status_code == 201, response.text
    report = response.json()['data']['id']

    response = owner_client.get(f'{REPORTS}{report}/', params={'include': 'task'})
    assert [it['id'] for it in response.json()['included']] == [str(own.pk)]

    response = stranger_client.get(f'{REPORTS}{report}/', params={'include': 'task'})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['data']['relationships']['task']['data']['id'] == str(own.pk)
    assert data.get('included', []) == []

    # staff see every task
    staff_client = get_api_client(sample_app, staff.jwt_build())
    response = staff_client.get(f'{REPORTS}{report}/', params={'include': 'task'})
    assert [it['id'] for it in response.json()['included']] == [str(own.pk)]
    assert staff_client.post(REPORTS, json_data=report_body(LogMessage.delay('system'))).status_code == 201


@pytest.mark.django_db(transaction=True)
def test_tasks_without_an_authenticated_user():
    """
    `restrict_queryset` never fails without a user: an anonymous user sees no task, a
    missing user is the authenticated user of the request, if any.
    """
    from bazis.contrib.bg.routes import BgRoute
    from bazis.contrib.users import get_anonymous_user_model
    from bazis.contrib.users.models_abstract import UserMixin
    from bazis.core.schemas import CrudAccessAction

    owner = User.objects.create_user('owner', password='weak_password_1')
    own = LogMessage.delay('own')
    Task.objects.filter(pk=own.pk).update(author=owner)

    def visible(**kwargs):
        return [it.pk for it in BgRoute.restrict_queryset(Task.objects.all(), CrudAccessAction.VIEW, **kwargs)]

    assert visible() == []
    assert visible(user=get_anonymous_user_model()()) == []
    assert visible(user=owner) == [own.pk]
    token = UserMixin.CTX_USER_REQUEST.set(owner)
    try:
        assert visible() == [own.pk]
    finally:
        UserMixin.CTX_USER_REQUEST.reset(token)
