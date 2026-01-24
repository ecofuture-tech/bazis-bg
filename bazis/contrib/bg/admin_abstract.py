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

from django import forms
from django.apps import apps
from django.contrib import admin, messages
from django.contrib.admin.helpers import ActionForm
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect

# from .models import Task, TaskCron
from django.urls import reverse
from django.utils.safestring import mark_safe

from bazis.contrib.author.admin_abstract import AuthorAdminMixin
from bazis.core.admin_abstract import AutocompleteMixin, DtAdminMixin

from . import REGISTRY_BG_TASKS
from .admin_tags import button_action, history, progress, spoiler


class LoadActionForm(ActionForm):
    file_load = forms.FileField(required=False)


def create_task_action(task, func_task=None):
    def func(self, request, queryset):
        task_obj = func_task(task, request, queryset) if func_task else task.delay()

        # Dynamic URL generation
        admin_url = reverse('admin:bg_task_change', args=[task_obj.id])

        # print('task_obj:', task_obj)
        messages.add_message(
            request,
            messages.SUCCESS,
            f'Started: <a href="{admin_url}" target="_blank">{task.get_name()}</a>',
        )

    func.short_description = task.get_name()
    return func


def task_load_action(task, request, queryset):
    return task.delay(fp=request.FILES.get('file_load', None))


class LoadDownloadAdminMetaclass(forms.MediaDefiningClass):
    def __new__(cls, clsname, bases, dct):
        # file export actions
        for task in dct.get('tasks_download', []):
            action_name = f'action_{task.__name__.lower()}'
            dct[action_name] = create_task_action(task)
            dct.setdefault('actions_task_download', []).append(action_name)
            dct.setdefault('actions', []).append(action_name)

        # file import actions
        for task in dct.get('tasks_load', []):
            action_name = f'action_{task.__name__.lower()}'
            dct[action_name] = create_task_action(task, func_task=task_load_action)
            dct.setdefault('actions_task_load', []).append(action_name)
            dct.setdefault('actions', []).append(action_name)

        # task processing actions
        for task in dct.get('tasks_handler', []):
            action_name = f'action_{task.__name__.lower()}'
            dct[action_name] = create_task_action(task)
            dct.setdefault('actions_task_handler', []).append(action_name)
            dct.setdefault('actions', []).append(action_name)

        return super().__new__(cls, clsname, bases, dct)


class LoadDownloadAdminMixin(metaclass=LoadDownloadAdminMetaclass):
    action_form = LoadActionForm
    tasks_load = []
    tasks_download = []
    tasks_handler = []
    show_full_result_count = False

    def changelist_view(self, request, *args, **kwargs):
        action = request.POST.get('action', None)
        # background task actions
        actions = (
            getattr(self, 'actions_task_download', [])
            + getattr(self, 'actions_task_load', [])
            + getattr(self, 'actions_task_handler', [])
        )
        # if an action is passed, emulate data submission
        if action and action in actions and not request.POST.getlist('_selected_action'):
            request.POST = request.POST.copy()
            request.POST['_selected_action'] = 0
            request.POST['select_across'] = 1

        return super().changelist_view(request, *args, **kwargs)

    # hack to set list_editable if it is missing, for get_changelist_formset
    def get_changelist_instance(self, request):
        cl = super().get_changelist_instance(request)
        if not cl.list_editable:
            cl.list_editable = (None,)
        return cl

    # hack to set is_multipart
    def get_changelist_formset(self, request, **kwargs):
        formset = super().get_changelist_formset(request, **kwargs)
        formset.is_multipart = True
        return formset

    class Media:
        js = ('admin/js/jquery-3.5.1.min.js', 'admin/js/file_load.js')


class TaskDoneFilter(admin.SimpleListFilter):
    title = 'Completed tasks'
    parameter_name = 'done_state'

    def lookups(self, request, model_admin):
        return [
            ('success', 'Successful'),
            ('error', 'With error'),
            ('interrupt', 'Interrupted'),
        ]

    def queryset(self, request, qs):
        val = self.value()
        # search only among completed ones
        done = qs.filter(state='done')
        # check each case
        if val == 'success':
            return done.filter(error__isnull=True, interrupt=False)
        elif val == 'error':
            return done.filter(error__isnull=False)
        elif val == 'interrupt':
            return done.filter(interrupt=True)
        return qs


class TaskClsFilter(admin.SimpleListFilter):
    title = 'Types of background tasks'
    parameter_name = 'cls_path'

    def lookups(self, request, model_admin):
        items = []
        for bg_path, bg_cls in REGISTRY_BG_TASKS.items():
            items.append((bg_path, bg_cls.get_name()))
        return items

    def queryset(self, request, queryset):
        try:
            return queryset.filter(**self.used_parameters)
        except (ValueError, ValidationError) as e:
            # Fields may raise a ValueError or ValidationError when converting
            # the parameters to the correct type.
            raise IncorrectLookupParameters(e) from e


class TaskCronFilter(admin.RelatedFieldListFilter):
    def __init__(self, field, request, params, model, model_admin, field_path, *args, **kwargs):
        # custom handling of an empty value
        without_cron = not params
        if without_cron:
            params['task_cron__isnull'] = ['True']
        super().__init__(field, request, params, model, model_admin, field_path)
        self.empty_value_display = 'Non-periodic'
        if without_cron:
            self.lookup_val_isnull = [True]
        # handling the special case of the entire selection
        if self.lookup_val == '0':
            self.used_parameters = {}

    def choices(self, changelist):
        for it in list(reversed(list(super().choices(changelist))))[:-1]:
            yield it
        it = {
            'selected': self.lookup_val == '0',
            'query_string': changelist.get_query_string(
                {self.lookup_kwarg: '0'},
                [self.lookup_kwarg_isnull],
            ),
            'display': 'All',
        }
        yield it


class TaskAdminBase(DtAdminMixin, AutocompleteMixin, AuthorAdminMixin, admin.ModelAdmin):
    list_per_page = 10
    list_display = (
        'name',
        'state',
        'phase',
        '_progress',
        '_phases_history',
        '_log',
        '_error',
        '_interrupting',
        '_file',
        'dt_start',
        'dt_finish',
    )
    readonly_fields = (
        'cls_path',
        'pid',
        'args',
        'kwargs',
        'state',
        'phase',
        'phases_history',
        'error',
        'interrupt',
        'dt_start',
        'dt_finish',
        'file',
        'log',
        'expected',
        'performed',
    )
    list_filter = (
        'state',
        TaskDoneFilter,
        TaskClsFilter,
        ('task_cron', TaskCronFilter),
    )

    def _file(self, task):
        if task.file:
            return mark_safe(f'<a href="{task.file.url}" download>{task.file.name}</a>')
        else:
            return '-'

    _file.short_description = 'Task file'

    def _error(self, task):
        return spoiler(task.error, 'red') if task.error else '-'

    _error.short_description = 'Error'

    def _interrupting(self, task):
        if not task.cls:
            return '-'

        if task.interrupt:
            return mark_safe('<div style="color: #fca400">Interrupted</div>')
        elif task.state == 'done':
            return '-'
        else:
            return button_action(
                'task_break',
                task.id,
                'Interrupt',
                confirm=f'ATTENTION! The task [{task.cls.get_name()}] will be interrupted!',
            )

    _interrupting.short_description = 'Interrupt'

    # progress of execution for the current phase
    def _progress(self, task):
        return progress(task)

    _progress.short_description = 'Progress'

    # progress of execution for the current phase
    def _phases_history(self, task):
        if not task.phases_history or not task.cls:
            return '-'
        return spoiler(history(task), 'blue')

    _phases_history.short_description = 'History'

    # execution log
    def _log(self, task):
        if not task.log:
            return '-'
        return spoiler(task.log, 'blue')

    _log.short_description = 'Log'

    def changelist_view(self, request, extra_context=None):
        if 'task_break' in request.POST:
            # get the task
            task = apps.get_model('bg.Task').objects.get(id=request.POST['task_break'])
            # interrupt execution
            task.interrupt = True
            # if the task is waiting to start - immediately change the status
            if task.state in ('waiting', 'starting'):
                task.state = 'done'
                task.phase = 'interrupted'
            # save the status
            task.save(update_fields=['interrupt', 'state', 'phase'])
            return HttpResponseRedirect(request.get_full_path())
        return super().changelist_view(request, extra_context)


class TaskCronForm(forms.ModelForm):
    cls_path = forms.ChoiceField(label='Background task')

    class Meta:
        model = apps.get_model('bg.TaskCron')
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cls_path'].choices = [
            (bg_path, bg_cls.get_name()) for bg_path, bg_cls in REGISTRY_BG_TASKS.items()
        ]


class TaskCronAdminBase(DtAdminMixin, AutocompleteMixin, AuthorAdminMixin, admin.ModelAdmin):
    list_display = ('name', 'cls_path', 'args', 'kwargs', 'period', 'dt_run', 'is_enable')
    list_editable = ('is_enable',)
    readonly_fields = ('dt_run',)
    form = TaskCronForm
