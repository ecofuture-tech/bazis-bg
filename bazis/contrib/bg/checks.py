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

from django.core.checks import Tags, Warning, register


@register()
def check_declarations(app_configs, **kwargs):
    """
    The schedules declared in the `schedules.py` modules: their slugs, names, periods and
    kwargs (bg.E001), their task classes and whether the kwargs fit them (bg.E002).
    """
    from .declare import declaration_messages, declarations

    return declaration_messages(declarations())


@register(Tags.database)
def check_declarations_applied(app_configs, databases=None, **kwargs):
    """
    The database has the periodic tasks as declared, and no managed one that is no longer
    declared (bg.W001): a warning, as `migrate` runs the database checks before it applies
    the declarations. Skipped while migrations are not applied.
    """
    from bazis.core.declare import migrations_complete

    from .declare import apply_declarations, declaration_messages, declarations

    schedules = declarations()
    if any(it.is_serious() for it in declaration_messages(schedules)):
        # bg.E001, bg.E002
        return []
    messages = []
    for using in databases or ():
        if not migrations_complete(using):
            continue
        if changes := apply_declarations(using, schedules, dry_run=True):
            messages.append(
                Warning(
                    f'The database {using} differs from the declared schedules: {"; ".join(changes)}.',
                    hint='Run `manage.py migrate`: it applies the declarations.',
                    id='bg.W001',
                )
            )
    return messages
