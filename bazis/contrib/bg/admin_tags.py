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
from django.utils.safestring import mark_safe


def task_is_run(cls):
    return apps.get_model('bg.Task').objects.filter(cls=cls).exclude(state='done').exists()


def task_is_success(task):
    return (task.state == 'done') and (not task.error) and (not task.interrupt)


def progress(task):
    if task.performed is None:
        return '-'

    d_names = dict(task.cls.d_names, **{'': 'Execution'})

    # convert to dicts
    expecteds = task.expected if isinstance(task.expected, dict) else {'': task.expected}
    performeds = task.performed if isinstance(task.performed, dict) else {'': task.performed}

    # determine intersection by keys
    slugs = set(list(expecteds.keys()) + list(performeds.keys()))

    # calculate progress bar height
    height = 35 if len(d_names) == 1 else 18
    font_size = 11 if len(d_names) == 1 else 9

    html = '<div style="position: relative; margin: -10px;">'
    for slug in slugs:
        expected = expecteds.get(slug, None) or 0
        performed = performeds.get(slug, None) or 0

        # if there is %, build the tag
        if expected:
            percent = f"""
                <div style="
                    position: absolute;
                    width: {(1.0 * performed / expected) * 100}%;
                    background-color: rgba(0, 255, 0, 0.5);
                    height: {height}px;
                    top: 0;
                    left: 0;
                    z-index: 1;"
                ></div>
            """
            count = f'{performed} / {expected}'
        else:
            percent = ''
            count = performed

        html += f"""
            <div style="position: relative;">
                <div style="
                    font-size: {font_size}px;
                    line-height: {height}px;
                    text-align: center;
                    font-weight: bold;
                    position: relative;
                    z-index: 2;
                    padding: 0 7px;
                ">{d_names[slug]}: {count}</div>
                {percent}
            </div>
        """

    html += '</div>'
    return mark_safe(html)


def history(task):
    d_names = dict(task.cls.d_names, **{'': 'Execution'})

    html = '<div>'
    for hist in task.phases_history:
        html += '<div>'
        html += '<div>{phase} ({duration} sec)</div>'.format(
            phase=hist['phase'],
            duration=hist['duration'],
        )

        # convert to dicts
        expecteds = (
            hist['expected'] if isinstance(hist['expected'], dict) else {'': hist['expected']}
        )
        performeds = (
            hist['performed'] if isinstance(hist['performed'], dict) else {'': hist['performed']}
        )

        # determine intersection by keys
        slugs = set(list(expecteds.keys()) + list(performeds.keys()))

        for slug in slugs:
            expected = expecteds.get(slug, None) or 0
            performed = performeds.get(slug, None) or 0

            # if there is %, build the tag
            if expected:
                count = f'{performed} / {expected}'
            else:
                count = performed

            if count:
                html += '<div>{name}: {count}</div>'.format(
                    name=d_names.get(slug, 'Not defined'),
                    count=count,
                )

        html += '<hr/></div>'
    html += '</div>'
    return mark_safe(html)


def spoiler(text, color):
    return mark_safe(
        f"""
        <a style="cursor: pointer; color: {color};"
           onclick="this.nextSibling.style.display = 'block'; this.style.display = 'none';"
       >Show</a><div style="display: none;">
            <a style="cursor: pointer;"
                onclick="this.parentElement.style.display='none';
                         this.parentElement.previousSibling.style.display='block';"
            >Hide</a>
            <pre style="color: {color}; font-size: 11px;">{text}</pre>
        </div>
    """
    )


def button_action(name, value, text, confirm=None):
    return mark_safe(
        '<button class="grp-button" style="width: auto;" name="{}" value="{}" {}>{}</button>'.format(
            name,
            value,
            (f'onclick="return confirm(\'{confirm}\')"') if confirm else '',
            text,
        )
    )
