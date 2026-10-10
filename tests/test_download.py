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
The files of the tasks (exports with personal data): stored under a random token, so that
the media host cannot be guessed, and served by `GET /api/v1/bg/task/{id}/download/` to
the author of the task and staff only.
"""

import uuid

from django.core.files.base import ContentFile
from django.core.management import call_command

import pytest
from bazis_test_utils.utils import get_api_client
from entity.bg.calc_data import ExportParents, LogMessage

from bazis.contrib.bg.models import Task
from bazis.contrib.bg.models_abstract import TASK_FILE_TOKEN, task_file_download_name
from bazis.contrib.users import get_user_model

from tests import factories


User = get_user_model()

TASKS = '/api/v1/bg/task/'
XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


def client_of(app, user=None):
    return get_api_client(app, user.jwt_build()) if user else get_api_client(app)


@pytest.mark.django_db(transaction=True)
def test_task_file_names_are_not_guessable(settings, tmp_path):
    """
    The name of an export was its file name and the time to the second: a client of the
    media host found it in at most 86 400 tries a day. The stored name starts with a
    random token; the download is named after the file without it.
    """
    settings.MEDIA_ROOT = str(tmp_path)
    factories.ParentEntityFactory.create_batch(2, child_entities=False)
    names = []
    for _ in range(2):
        task = ExportParents.delay()
        call_command('bg_task', task_id=task.id)
        task.refresh_from_db()
        assert task.is_success, task.error
        names.append(task.file.name)

    folder, stored = names[0].split('/')
    assert folder == settings.BAZIS_TASK_FOLDER
    match = TASK_FILE_TOKEN.match(stored)
    assert match, stored
    assert match['name'].startswith(f'{ExportParents.model.get_resource_name()}.')
    assert match['name'].endswith('.xlsx')
    # two exports of the same second differ by the token only
    assert names[0] != names[1]
    assert task_file_download_name(names[0]) == match['name']

    # a file given to delay(fp=...) is stored under its own name and a token
    upload = LogMessage.delay('upload', fp=ContentFile(b'data', name='/tmp/rows.xlsx'))
    assert TASK_FILE_TOKEN.match(upload.file.name.split('/', 1)[1])['name'] == 'rows.xlsx'
    # a name too long for the field is shortened after the token
    long = LogMessage.delay('long', fp=ContentFile(b'data', name=f'{"x" * 120}.xlsx'))
    assert len(long.file.name) <= Task._meta.get_field('file').max_length
    assert TASK_FILE_TOKEN.match(long.file.name.split('/', 1)[1])['name'].endswith('.xlsx')
    # a file stored before the token keeps its name
    assert task_file_download_name('bg/orders.2026-10-10_20-33-01.xlsx') == (
        'orders.2026-10-10_20-33-01.xlsx'
    )


@pytest.mark.django_db(transaction=True)
def test_download_is_for_the_author_and_staff(sample_app, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    owner = User.objects.create_user('owner', password='weak_password_1')
    stranger = User.objects.create_user('stranger', password='weak_password_2')
    staff = User.objects.create_user('staff', password='weak_password_3', is_staff=True)
    content = b'PK\x03\x04 rows of the export'
    task = LogMessage.delay(
        'export', author=owner, fp=ContentFile(content, name='participants.2026-10-10.xlsx')
    )
    url = f'{TASKS}{task.pk}/download/'

    assert client_of(sample_app).get(url).status_code == 401
    assert client_of(sample_app, stranger).get(url).status_code == 404

    for user in (owner, staff):
        response = client_of(sample_app, user).get(url)
        assert response.status_code == 200, response.text
        assert response.content == content
        assert response.headers['content-type'] == XLSX
        assert response.headers['content-disposition'] == (
            'attachment; filename="participants.2026-10-10.xlsx"'
        )
        assert response.headers['x-content-type-options'] == 'nosniff'
        assert response.headers['content-security-policy'] == 'sandbox'
        assert response.headers['cache-control'] == 'private, no-store'

    owner_client = client_of(sample_app, owner)
    assert owner_client.get(f'{TASKS}{uuid.uuid4()}/download/').status_code == 404
    # a task without a file
    no_file = LogMessage.delay('no file', author=owner)
    assert owner_client.get(f'{TASKS}{no_file.pk}/download/').status_code == 404
    # a file missing from the storage
    Task.objects.get(pk=task.pk).file.delete(save=False)
    assert owner_client.get(url).status_code == 404
