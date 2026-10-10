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
  system storage in `MEDIA_ROOT`), in the folder `BAZIS_TASK_FOLDER` (`bg`), stored as
  `<token>_<name>` with a random token (the media host serves them without a check, the
  token keeps their names from being guessed). Clients download them from
  `GET /api/v1/bg/task/{id}/download/` (see Rules).

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
- An export for the user of a request (an action of a route): the task runs in the
  handler process, without the request, its user or its language. Queue it with JSON
  arguments (ids, ISO dates) and `author=user`, so that the user reads the task at
  `/api/v1/bg/task/{id}/` and downloads its file from `/api/v1/bg/task/{id}/download/`;
  restrict the rows with the `restrict_queryset` of the default route of the model for
  that user; write the texts in the language of the request:

  ```python
  # the route: @http_post('/export/', kind=RouteKind.OTHER) def action_export(self, ...)
  task = OrdersExport.delay(user_id=str(user.pk), language=get_language(), author=user)

  class OrdersExport(BgBaseDownload):
      name = 'Orders'
      fields_read = ['number', 'title']
      file_name = 'orders'

      def __init__(self, user_id, language):
          self.user = get_user_model().objects.get(pk=user_id)
          self.language = language

      def handle(self):
          with translation.override(self.language):
              super().handle()

      def get_titles(self):           # column titles (lazy texts are written translated)
          return {'number': _('Number'), 'title': _('Title')}

      def queryset(self):
          qs = OrderRouteSet.restrict_queryset(Order.objects.all(), CrudAccessAction.VIEW,
                                               user=self.user)
          return qs.order_by('number')

      def get_count(self):            # required: the expected number of rows
          return self.queryset().count()

      def get_queryset(self):         # objects or dicts keyed by fields_read
          return self.queryset()
  ```
- Admin: `LoadDownloadAdminMixin` with `tasks_download`, `tasks_load`, `tasks_handler`
  (task classes, in the admin class body) adds actions that start them without arguments
  (`tasks_load` with the uploaded file).

## Periodic tasks and cleanup

A periodic task of a product is declared in the `schedules.py` module of an application,
not in the admin nor in a data migration:

```python
# training/schedules.py
from django.utils.translation import gettext_lazy as _
from bazis.contrib.bg.declare import Schedule

SCHEDULES = [
    Schedule('deadlines_remind', 'training.bg.deadlines.RemindDeadlines', '0 6 * * *',
             _('Deadline reminders'), kwargs={'days': 3}),
    Schedule('stats_refresh', StatsRefresh, 3600),      # the class, or its path
]
```

- `Schedule(slug, task, period, name=None, kwargs={}, enabled=True)`: `task` is a `BgBase`
  class with a `name` (or its path `module.Class`); `period` is seconds after the previous
  run finished (`3600`, `"3600"`) or a cron expression in UTC (`"0 3 * * *"`); `name` an
  English msgid stored in `LANGUAGE_CODE` (the name of the task class without it);
  `kwargs` the JSON keyword arguments of the task (not `name`, `fp`, `author`, `envs`).
  `TaskCron.name` is one column: the declared name is stored translated into
  `LANGUAGE_CODE` (a new `LANGUAGE_CODE` renames it at the next `migrate`).
- `migrate` applies them (`post_migrate`, also sent by `flush`) once all the migrations of
  the project are applied, in one transaction: the periodic task (`TaskCron`) of each slug
  is created or updated as declared and marked `managed`; a new period or `enabled`
  resets its next run time. Applied again it writes nothing. A periodic task of the slug
  that exists unmarked (made in the admin) is taken over with a warning in the log. A
  managed one no longer declared is disabled and unmarked: an ordinary periodic task the
  admin may enable again, not deleted (its tasks reference it). This differs from the
  roles of bazis-permit and the transits of bazis-statusy, which stay managed with a
  warning: a periodic task left enabled would keep running. Periodic tasks made in the
  admin are left as they are.
- A data migration with `TaskCron.objects.get_or_create(...)` is the wrong tool: it runs
  once, so a new period in the code never reaches a database that has the row, and it
  depends on the migrations of the package.
- Moving a periodic task made by such a migration (or in the admin) to `schedules.py`: its
  row has no slug, so the schedule creates a second enabled one and the task runs twice
  (`bg.W002` reports it). Delete the old row and let the declaration own the schedule: in
  the admin, or with a data migration of the product (keep the old migration; this works
  whether `migrate` has already created the declared row or not, as that one has a slug):

  ```python
  def delete_old_cron(apps, schema_editor):
      apps.get_model('bg', 'TaskCron').objects.filter(
          cls_path='training.bg.deadlines.RemindDeadlines', slug=None,
      ).delete()

  # depends on the old get_or_create migration and on ('bg', '0006_taskcron_slug_managed')
  operations = [migrations.RunPython(delete_old_cron, migrations.RunPython.noop)]
  ```

  Add `kwargs={...}` to the filter if other periodic tasks of the admin run the same class.
  The tasks the old row started are kept but no longer linked to a periodic task
  (`on_delete=SET_NULL`): the cleanup counts them as manual tasks (`BAZIS_TASK_LIFETIME`).
- The admin shows a declared periodic task read-only besides `dt_run` (setting it runs the
  task at that time) and `envs`, and does not delete it.
- Checks: `bg.E001` (the slug, a duplicate, the name, the period, the kwargs, `enabled`),
  `bg.E002` (the task class does not import, is not a named `BgBase`, or the kwargs do not
  fit its `__init__`); with a database (`bazis_doctor`) `bg.W001` (the database differs
  from the declarations: run `migrate`) and `bg.W002` (an enabled periodic task that is
  not managed runs the task of a schedule with its kwargs: delete it).
- Tests: the migrated test database has them; `bazis_test_utils` (`apply_declarations()`,
  the fixture `bazis_declared`) applies them again for a test that changes them.
- `bazis.contrib.bg.declare.apply_declarations(using, schedules=None, dry_run=False)`
  returns the changes; `dry_run` only lists them.
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
  include (the core, Bazis 2.7). `CTX_USER_REQUEST` is set by the routes of bazis-users
  (`UserRouteBase`) and its Django middleware: on a route without a user (a plain
  `JsonapiRouteBase`) a logged-in user is anonymous for the tasks (403 for his own task,
  left out of `included`). A model with a foreign key to `bg.Task` (the sample
  `entity.Report`) links only the tasks the user sees (403 `ERR_RELATION_ACCESS`
  otherwise) and `include` leaves out the others; its route set needs no checks of its
  own. A custom task route of `bg.Task` changes the rule in `restrict_queryset` and
  declares `default_route = True`.
- `GET /api/v1/bg/task/{id}/download/` serves the file of a task the user sees (401 for an
  anonymous user, 404 for another user's task, a task without a file or a file missing from
  the storage) as a download named after the file without its token, with `nosniff`,
  `Content-Security-Policy: sandbox` and `Cache-Control: private, no-store`. Link the
  file to this route, not to the `file` attribute: that is the URL of the media host,
  which serves it to anyone who has the link. A custom task route that lists its
  `actions` adds `action_download`.
- `BgRoute` and its subclasses restrict the tasks with their own `restrict_queryset`:
  `permit.W002` of bazis-permit does not apply to them from bazis-permit 2.10 (do not
  declare `permit_public = True`, which says the data is public). With bazis-permit 2.9
  the warning is a false positive.
- A task class is found by its path (`module.Class`): the scheduler deletes waiting tasks
  whose class does not import, so keep the path when tasks may be queued.
- A task with the same arguments as a running task of its class waits for it.
- A handler runs many tasks in one process: release what a task attaches to global state
  (loggers, settings, connections).
