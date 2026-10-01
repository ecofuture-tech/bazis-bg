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
