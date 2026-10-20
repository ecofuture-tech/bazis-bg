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

import mimetypes

from django.apps import apps
from django.db.models import QuerySet
from django.utils.http import content_disposition_header
from django.utils.translation import gettext as _

from fastapi import HTTPException

from starlette.responses import StreamingResponse

from bazis.contrib.author.routes_abstract import AuthorRequiredRouteBase
from bazis.contrib.users.models_abstract import UserMixin
from bazis.core.routes_abstract.initial import http_get
from bazis.core.routes_abstract.jsonapi import RestrictedQsRouteMixin
from bazis.core.routes_abstract.jsonapi.callbacks import JsonApiResponse
from bazis.core.schemas import AccessAction, CrudAccessAction
from bazis.core.schemas.enums import RouteKind

from .models_abstract import task_error_summary, task_file_download_name


#: the size of the chunks a download reads from the storage
DOWNLOAD_CHUNK_SIZE = 64 * 1024


def task_accepted(task) -> JsonApiResponse:
    """
    The answer of an action that queued a task: 202, its identifier
    (`{"data": {"type": "bg.task", "id": ...}}`) and the URL of the task in its default route
    as `Location` (`/api/v1/bg/task/{id}/`), which the client polls until it is done.
    """
    url = type(task).get_default_route().url_path_for('action_retrieve', item_id=str(task.pk))
    return JsonApiResponse(
        {'data': {'type': task.get_resource_label(), 'id': str(task.pk)}},
        status_code=202,
        headers={'Location': url},
    )


class BgRoute(RestrictedQsRouteMixin, AuthorRequiredRouteBase):
    """
    The background tasks of the user (staff see all tasks): their arguments, logs and files
    are private. As the default route of the tasks, its `restrict_queryset` is also what
    the other routes link and include (bazis 2.7). The author reads the class of an error
    only and no log (`hide_internals`): the traceback and the log are for staff.
    """

    model = apps.get_model('bg.Task')
    actions = ['action_list', 'action_retrieve', 'action_download']

    @classmethod
    def restrict_queryset(
        cls, qs: QuerySet, access_action: AccessAction, user=None, **kwargs
    ) -> QuerySet:
        """
        The tasks of the user, all tasks for staff, for every action. Without a user (a
        route without a user, e.g. called by the core for the relationships of another
        route) the authenticated user of the request (`UserMixin.authenticated_user`); none
        for an anonymous user.
        """
        if (user := UserMixin.authenticated_user(user)) is None:
            return qs.none()
        qs = super().restrict_queryset(qs, access_action, user=user, **kwargs)
        return qs if user.is_staff else qs.filter(author=user)

    @classmethod
    def query_fields(cls, user=None, **kwargs):
        """
        The filter and the sorting of a user who is not staff do not reach the error and the
        log (`hide_internals`): a filter by their text would read them.
        """
        fields = super().query_fields(user=user, **kwargs)
        if (user := UserMixin.authenticated_user(user)) is not None and user.is_staff:
            return fields
        return [it for it in fields if it.source not in ('error', 'log')]

    @http_get(
        '/{item_id}/download/',
        kind=RouteKind.OTHER,
        response_class=StreamingResponse,
        responses={200: {'content': {'application/octet-stream': {}}, 'description': 'The file'}},
    )
    def action_download(self, item_id: str, **kwargs):
        """
        The file of a task the user sees (`get_queryset`: his own tasks, all for staff), read
        from the storage: 404 for another task, a task without a file or a file missing from
        the storage. Always a download named after the file (without its token), with
        `nosniff`, a sandbox and no caching: an export holds personal data.
        """
        item = self.set_item(item_id)
        try:
            stream = item.file.open('rb')
        except (OSError, ValueError):
            raise HTTPException(status_code=404, detail=_('Item not found')) from None

        def chunks():
            try:
                yield from stream.chunks(DOWNLOAD_CHUNK_SIZE)
            finally:
                stream.close()

        return StreamingResponse(
            chunks(),
            media_type=mimetypes.guess_type(item.file.name)[0] or 'application/octet-stream',
            headers={
                'Content-Disposition': content_disposition_header(
                    True, task_file_download_name(item.file.name)
                ),
                'X-Content-Type-Options': 'nosniff',
                'Content-Security-Policy': 'sandbox',
                'Cache-Control': 'private, no-store',
            },
        )

    def get_queryset(self):
        return self.restrict_queryset(
            super().get_queryset(), CrudAccessAction.VIEW, user=self.inject.user
        )

    def hide_internals(self, task):
        """
        For a user who is not staff, the loaded task (never saved: the route reads only)
        holds the class of its error instead of the traceback and no log: they hold paths,
        code and data of the server.
        """
        if not self.inject.user.is_staff:
            if 'error' not in task.get_deferred_fields():
                task.error = task_error_summary(task.error)
            task.log = None
        return task

    def list(self):
        qs = super().list()
        for task in qs:
            self.hide_internals(task)
        return qs

    def retrieve(self, item_id: str, with_lock: bool = False, is_force: bool = False):
        return self.hide_internals(super().retrieve(item_id, with_lock, is_force))
