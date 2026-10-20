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
The task route for the author of a task and staff: the traceback of an error and the log
hold paths, code and data of the server, so the author reads only that the task failed;
a product action that queues a task answers 202 and the client follows the task.
"""

from traceback import format_exc

from django.core.files.base import ContentFile
from django.core.management import call_command

import pytest
from bazis_test_utils.utils import get_api_client
from entity.bg.calc_data import LogMessage

from bazis.contrib.bg.basic.base import BgBase
from bazis.contrib.bg.models import Task
from bazis.contrib.users import get_user_model

from tests import factories


User = get_user_model()

TASKS = '/api/v1/bg/task/'
REPORTS = '/api/v1/entity/report/'


def client_of(app, user=None):
    return get_api_client(app, user.jwt_build()) if user else get_api_client(app)


class Fails(BgBase):
    name = 'Fails'

    def handle(self):
        self.log.info('reading /srv/app/secret.py')
        # a database error: the message quotes the row on its last line
        raise ValueError('duplicate key\nDETAIL:  Key (email)=(secret@example.com) exists.')


def attributes(response):
    assert response.status_code == 200, response.text
    return response.json()['data']['attributes']


def listed(response):
    assert response.status_code == 200, response.text
    return {it['id']: it['attributes'] for it in response.json()['data']}


@pytest.mark.django_db(transaction=True)
def test_the_author_reads_only_that_the_task_failed(sample_app, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    owner = User.objects.create_user('owner', password='weak_password_1')
    stranger = User.objects.create_user('stranger', password='weak_password_2')
    staff = User.objects.create_user('staff', password='weak_password_3', is_staff=True)
    failed = Fails.delay(author=owner, fp=ContentFile(b'rows', name='rows.xlsx'))
    call_command('bg_task', task_id=failed.id)
    traceback = Task.objects.get(pk=failed.pk).error
    log = Task.objects.get(pk=failed.pk).log
    assert traceback.startswith('Traceback') and 'secret@example.com' in traceback
    assert '/srv/app/secret.py' in log
    done = LogMessage.delay('done', author=owner)
    call_command('bg_task', task_id=done.id)
    # an error written without a traceback (bg_handler, bg_scheduler)
    lost = LogMessage.delay('lost', author=owner)
    Task.objects.filter(pk=lost.pk).update(state='done', error='Uncaught execution error')
    empty = LogMessage.delay('empty', author=owner)
    Task.objects.filter(pk=empty.pk).update(error='')

    owner_client = client_of(sample_app, owner)
    item = attributes(owner_client.get(f'{TASKS}{failed.pk}/'))
    assert (item['error'], item['log']) == ('Error', None)
    assert item['state'] == 'done'
    items = listed(owner_client.get(TASKS))
    assert (items[str(failed.pk)]['error'], items[str(failed.pk)]['log']) == ('Error', None)
    assert (items[str(done.pk)]['error'], items[str(done.pk)]['log']) == (None, None)
    assert items[str(lost.pk)]['error'] == 'Error'
    assert items[str(empty.pk)]['error'] == ''
    # the filter and the sorting do not reach them either
    for field in ('error', 'log'):
        response = owner_client.get(TASKS, params={'filter': f'{field}__iregex=secret'})
        assert response.status_code == 400, response.text
        assert response.json()['errors'][0]['code'] == 'ERR_FILTER'
        assert owner_client.get(TASKS, params={'sort': field}).status_code == 400
    # nor through the relation of another route
    report = {'type': 'entity.report', 'attributes': {'title': 'Report'}}
    report['relationships'] = {'task': {'data': {'type': 'bg.task', 'id': str(failed.pk)}}}
    assert owner_client.post(REPORTS, json_data={'data': report}).status_code == 201
    by_error = {'filter': 'task__error__iregex=secret'}
    assert owner_client.get(REPORTS, params=by_error).status_code == 400

    staff_client = client_of(sample_app, staff)
    item = attributes(staff_client.get(f'{TASKS}{failed.pk}/'))
    assert (item['error'], item['log']) == (traceback, log)
    assert listed(staff_client.get(TASKS))[str(failed.pk)]['error'] == traceback
    response = staff_client.get(TASKS, params={'filter': 'error__iregex=secret'})
    assert list(listed(response)) == [str(failed.pk)]
    assert len(listed(staff_client.get(REPORTS, params=by_error))) == 1

    assert client_of(sample_app, stranger).get(f'{TASKS}{failed.pk}/').status_code == 404
    assert listed(client_of(sample_app, stranger).get(TASKS)) == {}

    # the reads change nothing; the file is still downloaded
    assert Task.objects.get(pk=failed.pk).error == traceback
    response = owner_client.get(f'{TASKS}{failed.pk}/download/')
    assert (response.status_code, response.content) == (200, b'rows')


def formatted(fail):
    """The traceback of the exception that `fail` raises, as the handler writes it."""
    try:
        fail()
    except Exception:  # NOQA [B902]
        return format_exc()


def raise_(exception):
    raise exception


def noted():
    exception = ValueError('message')
    exception.add_note('secret_note')
    raise exception


def chained():
    try:
        {}['secret_key']
    except KeyError:
        raise_(TypeError('secret_token'))


def caused():
    try:
        {}['secret_key']
    except KeyError as e:
        raise ValueError('secret_token') from e


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    'fail',
    [
        lambda: raise_(ValueError('failed for\nsecret_token_abc')),
        lambda: raise_(ValueError('x\n  File "/srv/secret.py", line 1, in f\nsecret_token')),
        noted,
        chained,
        caused,
        # a message that quotes the traceback of a worker
        lambda: raise_(RuntimeError(
            'worker failed:\nTraceback (most recent call last):\n'
            '  File "/srv/secret.py", line 1, in f\nsecret_word'
        )),
    ],
)
def test_the_author_reads_nothing_of_the_text_of_an_error(sample_app, fail):
    """No message, note, path or part of a traceback in the text, however it is written."""
    owner = User.objects.create_user('owner', password='weak_password_1')
    task = LogMessage.delay('x', author=owner)
    error = formatted(fail)
    assert 'secret' in error
    Task.objects.filter(pk=task.pk).update(state='done', error=error)

    response = client_of(sample_app, owner).get(TASKS)
    assert listed(response)[str(task.pk)]['error'] == 'Error'
    assert 'secret' not in response.text


@pytest.mark.django_db(transaction=True)
def test_a_client_follows_the_task_of_an_action(sample_app):
    """
    The sample action queues a task and answers 202 with its id and its URL: the client
    polls the task route until the task is done.
    """
    factories.ParentEntityFactory.create_batch(3, child_entities=False)
    user = User.objects.create_user('user', password='weak_password_1')
    client = client_of(sample_app, user)

    response = client.post(f'{REPORTS}calc/')
    assert response.status_code == 202, response.text
    assert response.headers['content-type'] == 'application/vnd.api+json'
    data = response.json()['data']
    assert data['type'] == 'bg.task'
    url = f'{TASKS}{data["id"]}/'
    assert response.headers['location'] == url
    assert Task.objects.get(pk=data['id']).author == user

    task = attributes(client.get(url))
    assert task['state'] == 'waiting'

    call_command('bg_task', task_id=data['id'])

    task = attributes(client.get(url))
    assert (task['state'], task['error']) == ('done', None)
    assert (task['expected'], task['performed']) == (None, None)
    assert [
        (it['phase'], it['expected'], it['performed']) for it in task['phases_history']
    ] == [('First phase: parents', 3, 3)]
