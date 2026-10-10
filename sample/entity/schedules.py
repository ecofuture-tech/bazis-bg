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
The periodic tasks of the sample (bazis.contrib.bg.declare), applied by `migrate`.
"""

from django.utils.translation import gettext_lazy as _

from bazis.contrib.bg.declare import Schedule


SCHEDULES = [
    Schedule(
        'entity_log_hourly', 'entity.bg.calc_data.LogMessage', 3600, _('Log a message hourly'),
        kwargs={'message': 'hourly'},
    ),
]
