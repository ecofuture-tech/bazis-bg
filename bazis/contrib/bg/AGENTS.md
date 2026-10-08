# bazis-bg — guide for AI agents

Background tasks stored in PostgreSQL (no broker): a task class is queued with `delay()`
as a `Task` row, the `bg_scheduler` process starts handler processes that run the tasks,
schedules periodic tasks (`TaskCron`) and enforces the limits of each class. Also bases for
xlsx exports and imports. Needs bazis-author (tasks have an `author`).

## Setup

- `BS_INSTALLED_APPS` includes `bazis.contrib.bg`; `python manage.py migrate`.
- Put the task classes in `<app>/bg/*.py`: every module of the `bg` package of an installed
  app is imported at startup.
- Run one `python manage.py bg_scheduler` in the directory of `manage.py`: it starts
  `manage.py bg_handler --host 127.0.0.1 --port <port>` processes to keep
  `BAZIS_TASK_HANDLERS_LOCAL` (5) registered handlers, on free ports from
  `BAZIS_TASK_HANDLER_PORT` (49100), and serves `/healthcheck` on
  `BAZIS_TASK_SCHEDULER_PORT` (49001). A handler runs one task at a time and exits after
  2–4 hours (the scheduler starts another). Without the scheduler, tasks stay `waiting`.
- `python manage.py bg_task --task_id <id>` runs one task in the current process (tests,
  debugging).
- Files of tasks: `BS_BAZIS_STORAGE_BG` (import path of a storage class; default the file
  system storage in `MEDIA_ROOT`), in the folder `BAZIS_TASK_FOLDER` (`bg`).

## Tasks

```python
from bazis.contrib.bg.basic.base import BgBase

class Recalc(BgBase):
    name = 'Recalculate prices'     # required (the admin lists only named classes)
    parallel = 1                    # at most N running tasks of this class
    blocked = ['shop.bg.tasks.Import']   # wait while these classes (module.Class) run

    def __init__(self, category_id):    # the args/kwargs of delay()
        self.category_id = category_id

    def handle(self):
        qs = Product.objects.filter(category_id=self.category_id)
        self.next_phase('Prices', expected=qs.count())
        for product in qs:
            ...
            self.progress()          # saved to the task every 3 s; checks the interruption
        self.set_result({'count': qs.count()})

task = Recalc.delay(category_id, author=user)   # -> Task (state `waiting`)
```

- `delay()` arguments are stored as JSON. Reserved keyword arguments: `name`, `fp` (a file
  saved to `task.file`), `author`, `envs` (stored, not applied).
- States: `waiting` → `starting` → `running` → `done`; `task.is_success`, `is_error`
  (`error` holds the traceback), `is_interrupt`; `phase`, `log`, `result`, `file`.
- Hooks: `pre_handle`, `post_handle`, `excepting` (error), `interrupting`, `finishing`
  (always). The admin "Interrupt" button sets `interrupt`; the task stops at its next
  `progress` sync, `next_phase`, `flush` or `set_result`.
- `is_transaction = True` (default) runs the task with autocommit off, but every
  `next_phase`, `flush`, `set_result` (and synced `progress`) commits the work done so far;
  an error rolls back only since the last commit.
- Exports: `BgBaseDownloadModel` (`model`, `fields_read`; all objects, override
  `get_queryset`) or `BgBaseDownload` (`fields_read`, `get_queryset`, `get_count`,
  `get_titles`, `file_name`) write xlsx to `task.file` (a zip above `limit_rows_split`
  rows). Imports: `BgBaseLoad` reads the `.xlsx` (or `.zip` of them) given as `delay(fp=...)` and passes
  the rows as dicts keyed by `fields_read` to `load(reader)`; `skip_titles = True` skips
  the header row.
- Admin: `LoadDownloadAdminMixin` with `tasks_download`, `tasks_load`, `tasks_handler`
  (task classes, in the admin class body) adds actions that start them without arguments
  (`tasks_load` with the uploaded file).

## Periodic tasks and cleanup

- `TaskCron(name, cls_path, args, kwargs, period, is_enable)` in the admin or in code:
  `period` is seconds after the previous run finished (`"3600"`) or a cron expression in
  UTC (`"0 3 * * *"`); an invalid one is written to its `error`. Setting `dt_run` runs it
  at that time.
- `python manage.py cleanup_init` creates the cleanup cron task: it deletes the tasks (and
  their files) not updated for `BAZIS_TASK_LIFETIME` (manual) or `BAZIS_TASK_CRON_LIFETIME`
  (periodic) seconds; its period is `BAZIS_TASK_CRON_CLEANUP` when the command runs. These
  three settings are dynamic (edited in the admin).

## Rules

- The task route of `bazis.contrib.bg.router` requires authentication and shows a user only
  the tasks whose `author` he is (staff see all): tasks hold arguments, logs and files.
  The author is set by `delay(author=user)` or, inside the API routes, from the current
  user; tasks queued elsewhere (admin, scheduler, scripts) have no author and only staff
  see them. Keep custom task routes as restrictive.
- The rule is the classmethod `BgRoute.restrict_queryset` (none for an anonymous user; the
  authenticated user of the request `UserMixin.CTX_USER_REQUEST` when the caller passes
  no user): as the default route of `bg.Task` it is also what the other routes link and
  include (the core, Bazis 2.7). A model with a foreign key to `bg.Task` (the sample
  `entity.Report`) links only the tasks the user sees (403 `ERR_RELATION_ACCESS`
  otherwise) and `include` leaves out the others; its route set needs no checks of its
  own. A custom task route of `bg.Task` changes the rule in `restrict_queryset` and
  declares `default_route = True`.
- A task class is found by its path (`module.Class`): the scheduler deletes waiting tasks
  whose class does not import, so keep the path when tasks may be queued.
- A task with the same arguments as a running task of its class waits for it.
- A handler runs many tasks in one process: release what a task attaches to global state
  (loggers, settings, connections).
