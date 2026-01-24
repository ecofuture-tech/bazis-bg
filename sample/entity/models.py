from django.db import models
from django.utils.translation import gettext_lazy as _

from bazis_test_utils.models_abstract import (
    ChildEntityBase,
    DependentEntityBase,
    ExtendedEntityBase,
    ParentEntityBase,
)

from bazis.core.models_abstract import DtMixin, JsonApiMixin, UuidMixin


class ChildEntity(DtMixin, UuidMixin, JsonApiMixin, ChildEntityBase):
    class Meta:
        verbose_name = _('Child entity')
        verbose_name_plural = _('Child entities')


class DependentEntity(DtMixin, UuidMixin, JsonApiMixin, DependentEntityBase):
    parent_entity = models.ForeignKey(
        'ParentEntity', on_delete=models.CASCADE, related_name='dependent_entities'
    )

    class Meta:
        verbose_name = _('Dependent entity')
        verbose_name_plural = _('Dependent entities')


class ExtendedEntity(DtMixin, UuidMixin, JsonApiMixin, ExtendedEntityBase):
    parent_entity = models.OneToOneField(
        'ParentEntity', on_delete=models.CASCADE, related_name='extended_entity'
    )

    class Meta:
        verbose_name = _('Extended entity')
        verbose_name_plural = _('Extended entities')


class ParentEntity(DtMixin, UuidMixin, JsonApiMixin, ParentEntityBase):
    s = models.TextField
    child_entities = models.ManyToManyField(
        ChildEntity,
        related_name='parent_entities',
        blank=True,
    )

    class Meta:
        verbose_name = _('Parent entity')
        verbose_name_plural = _('Parent entities')
