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


class Report(DtMixin, UuidMixin, JsonApiMixin):
    """
    A report that references the background task that built it: a user links only a task
    he can see (his own, any for staff) and reads it with `include=task` (the core checks
    the relationship and `included` against the default route of the tasks).
    """

    title = models.CharField(_('Title'), max_length=255)
    task = models.ForeignKey(
        'bg.Task', blank=True, null=True, on_delete=models.SET_NULL, related_name='+'
    )

    class Meta:
        verbose_name = _('Report')
        verbose_name_plural = _('Reports')
