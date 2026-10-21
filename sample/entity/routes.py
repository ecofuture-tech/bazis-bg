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

from bazis.contrib.bg.routes import task_accepted
from bazis.contrib.users.routes_abstract import UserRequiredRouteBase
from bazis.core.routes_abstract.initial import http_post
from bazis.core.schemas.enums import RouteKind

from .bg.calc_data import CalcData


class ReportRouteSet(UserRequiredRouteBase):
    """
    The reports: every user who is logged in reads and changes them all. The tasks they
    link and include are restricted by the default route of the tasks (BgRoute), the route
    set has no checks of its own.
    """

    model = apps.get_model('entity.Report')

    @http_post('/calc/', status_code=202, kind=RouteKind.OTHER)
    def action_calc(self, **kwargs):
        """Queues the calculation: the client follows the task at the URL of the answer."""
        return task_accepted(CalcData.delay(author=self.inject.user))
