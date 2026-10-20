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

from bazis.contrib.bg.basic.base import BgBase

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


class TwoPhases(BgBase):
    """Records the progress of its task as a client reads it, at each step."""

    name = 'Two phases'

    def handle(self):
        seen = []
        self.next_phase('First', expected=2)
        seen.append(self.read())
        self.progress(need_sync=True)
        seen.append(self.read())
        self.next_phase('Second', expected={'rows': 5})
        seen.append(self.read())
        self.set_result(seen)

    def read(self):
        task = self.get_task()
        return [task.phase, task.expected, task.performed, [it['phase'] for it in task.phases_history]]


@pytest.mark.django_db(transaction=True)
def test_progress_of_the_current_phase_and_the_history():
    """
    `expected` and `performed` are those of the current phase (`performed` from its first
    sync); a phase that ends is moved to `phases_history` and clears both, so they are null
    once the task is done.
    """
    task = TwoPhases.delay()
    call_command('bg_task', task_id=task.id)
    task.refresh_from_db()

    assert task.is_success, task.error
    assert task.result == [
        ['First', 2, None, []],
        ['First', 2, 1, []],
        ['Second', {'rows': 5}, None, ['First']],
    ]
    assert (task.expected, task.performed) == (None, None)
    assert [(it['phase'], it['expected'], it['performed']) for it in task.phases_history] == [
        ('First', 2, 1),
        ('Second', {'rows': 5}, None),
    ]
