from django.apps import apps
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--task_id', action='store', dest='task_id', default=None)

    def handle(self, task_id, **kwargs):
        Task = apps.get_model('bg.Task') # noqa F806
        task = Task.objects.get(id=task_id)
        task.cls.run(task, *task.args, **task.kwargs)
