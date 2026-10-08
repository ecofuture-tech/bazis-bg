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

from django.apps import apps
from django.db.models import QuerySet

from bazis.contrib.author.routes_abstract import AuthorRequiredRouteBase
from bazis.contrib.users.models_abstract import UserMixin
from bazis.core.routes_abstract.jsonapi import RestrictedQsRouteMixin
from bazis.core.schemas import AccessAction, CrudAccessAction


class BgRoute(RestrictedQsRouteMixin, AuthorRequiredRouteBase):
    """
    The background tasks of the user (staff see all tasks): their arguments, logs and files
    are private. As the default route of the tasks, its `restrict_queryset` is also what
    the other routes link and include (bazis 2.7).
    """

    model = apps.get_model('bg.Task')
    actions = ['action_list', 'action_retrieve']

    @classmethod
    def restrict_queryset(
        cls, qs: QuerySet, access_action: AccessAction, user=None, **kwargs
    ) -> QuerySet:
        """
        The tasks of the user, all tasks for staff, for every action. Without a user (a
        route without a user, e.g. called by the core for the relationships of another
        route) the authenticated user of the request (`UserMixin.CTX_USER_REQUEST`); none
        for an anonymous user.
        """
        if user is None:
            user = UserMixin.CTX_USER_REQUEST.get()
        if user is None or user.is_anonymous:
            return qs.none()
        qs = super().restrict_queryset(qs, access_action, user=user, **kwargs)
        return qs if user.is_staff else qs.filter(author=user)

    def get_queryset(self):
        return self.restrict_queryset(
            super().get_queryset(), CrudAccessAction.VIEW, user=self.inject.user
        )
