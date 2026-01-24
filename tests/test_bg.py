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
