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

from django.core.management import call_command

import pytest
from entity.bg.calc_data import CalcData

from tests import factories


@pytest.mark.django_db(transaction=True)
def test_bg():
    factories.ParentEntityFactory.create_batch(15, child_entities=True)

    task = CalcData.delay()
    assert task.state == 'waiting'

    call_command('bg_task', task_id=task.id)

    task.refresh_from_db()
    assert task.state == 'done'

    phases_history = task.phases_history
    assert len(phases_history) == 1

    phase = phases_history[0]
    assert phase['expected'] == phase['performed'] == 15

    assert all(
        parent.is_active for parent in factories.ParentEntityFactory._meta.model.objects.all()
    )
