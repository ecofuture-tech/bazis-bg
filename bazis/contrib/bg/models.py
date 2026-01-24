from bazis.contrib.bg.models_abstract import (
    TaskBase,
    TaskCronBase,
    TaskHandlerBase,
    task_file_name,  # noqa F401
)


class Task(TaskBase):
    pass


class TaskCron(TaskCronBase):
    pass


class TaskHandler(TaskHandlerBase):
    pass
