# bazis-bg

Background tasks for Bazis on PostgreSQL: a task class (`BgBase` and the export/import bases
in `basic/`) is queued with `delay()` as a `Task` row; the `bg_scheduler` command starts
local `bg_handler` processes, schedules cron tasks (`TaskCron`) and moves waiting tasks to
`starting` within the `parallel`/`blocked` limits of their classes; a handler takes one task
at a time (`select_for_update(skip_locked=True)`) and runs it in its own process.

A handler process runs many tasks one after another: anything a task attaches to global
state (loggers, settings, connections) must be released when it ends.

The package code is in `bazis/contrib/bg`, the sample project used by the tests is in `sample/`,
the tests are in `tests/`.

## Running the tests

The tests need PostgreSQL with PostGIS and Redis (see `.github/workflows/tests.yml`).
Run them from the `sample` directory:

```bash
cd sample
BS_DEBUG=true \
BS_SECRET_KEY=local-secret-key-that-is-long-enough-0123456789 \
BS_DATABASES__DEFAULT__HOST=localhost BS_DATABASES__DEFAULT__PORT=5432 \
BS_DATABASES__DEFAULT__NAME=bazis BS_DATABASES__DEFAULT__USER=postgres \
BS_DATABASES__DEFAULT__PASSWORD=postgres \
BS_CACHES__DEFAULT__LOCATION=redis://localhost:6379/1 \
BS_MEDIA_ROOT=/tmp/bazis/media BS_STATIC_ROOT=/tmp/bazis/static BS_WEBAPP_ROOT=/tmp/bazis/webapp \
python -m pytest ../tests -o addopts="" -p no:cacheprovider
```

Lint: `ruff check bazis tests sample`. CI also runs `python manage.py makemigrations --check
--dry-run` in `sample`: commit the migrations of model changes, including the sample apps.

## Releasing

A release is the tag `vX.Y.Z` on `main`: the Build and Publish workflow builds the package
(the version comes from the tag through setuptools-scm) and publishes it to PyPI
(pre-releases `-alphaN`/`-betaN`/`-rcN` go to Test PyPI) and creates the GitHub release.

Claude Code sessions cannot push tags. Release through the **Release** workflow instead:

1. Make sure the changes are merged into `main` and the Tests workflow is green on the
   `main` head commit (the Release workflow checks this and refuses otherwise).
2. Add the release notes as `docs/releases/X.Y.Z.md` in the change being released.
3. Start the workflow `release.yml` on `ref: main` with the input `version: X.Y.Z`
   (GitHub API: `POST /repos/ecofuture-tech/bazis-bg/actions/workflows/release.yml/dispatches`;
   with the GitHub MCP tools: `actions_run_trigger`, method `run_workflow`).
4. The Release run creates the annotated tag and starts Build and Publish on it. Check
   that both runs succeed and that the version appears on https://pypi.org/project/bazis-bg/.

Release the Bazis packages in dependency order: a package is tested in CI against the
versions of its Bazis dependencies published on PyPI. Pick the version by semver:
breaking changes (settings renamed or required, dependency removed, behavior changed)
bump the minor version while the project is below 3.0.
