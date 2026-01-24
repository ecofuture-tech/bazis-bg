from django.utils.translation import gettext_lazy as _

from bazis.contrib.bg.basic.base import BgBase

from entity.models import ParentEntity


class CalcData(BgBase):
    name = _('Calc data')
    parallel = 1

    def handle(self) -> None:
        qs = ParentEntity.objects.all()
        self.next_phase(phase_name='First phase: parents', expected=qs.count())

        for parent in ParentEntity.objects.all():
            parent.is_active = True
            parent.save()
            self.progress()
