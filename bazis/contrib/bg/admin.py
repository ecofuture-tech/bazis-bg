from django.contrib import admin

from .admin_abstract import TaskAdminBase, TaskCronAdminBase
from .models import Task, TaskCron


@admin.register(Task)
class TaskAdmin(TaskAdminBase):
    pass


@admin.register(TaskCron)
class TaskCronAdmin(TaskCronAdminBase):
    pass
