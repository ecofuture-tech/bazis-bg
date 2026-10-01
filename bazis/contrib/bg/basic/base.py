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

import logging
import traceback
from io import BufferedIOBase, StringIO
from time import sleep, time

from django.apps import apps
from django.db import transaction
from django.utils.timezone import now

from .. import REGISTRY_BG_TASKS


LOG = logging.getLogger(__name__)


class InterruptException(Exception):  # NOQA [N818]
    pass


class BgLogHandler(logging.StreamHandler):

    def __init__(self, io):
        super().__init__(io)
        # set formatter
        self.formatter = logging.Formatter("%(levelname)s:%(asctime)s:%(message)s")


def commit(using=None):
    if not transaction.get_connection(using).in_atomic_block:
        transaction.commit(using)


def rollback(using=None):
    if not transaction.get_connection(using).in_atomic_block:
        transaction.rollback(using)


def set_autocommit(autocommit, using=None):
    if not transaction.get_connection(using).in_atomic_block:
        transaction.set_autocommit(autocommit, using=using)


class BgBaseMeta(type):

    def __new__(mcs, name: str, bases: tuple, attrs: dict, **kwargs):
        # create class
        bg_cls: type[BgBase] = super().__new__(mcs, name, bases, attrs, **kwargs)

        # determine task name
        try:
            bg_name = bg_cls.get_name()
        except Exception:
            bg_name = None
        # further logic only for concrete classes
        if not bg_name:
            return bg_cls

        REGISTRY_BG_TASKS[bg_cls.get_path()] = bg_cls

        return bg_cls


class BgBase(metaclass=BgBaseMeta):
    # human-readable task name
    name = None
    # number of simultaneously running tasks
    parallel = 1
    # tasks that block execution
    blocked = []
    # naming dictionary
    d_names = {
        '': 'Execution',
    }
    # whether it should be processed in a transaction
    is_transaction = True
    # current task id
    task_id = None

    log = None

    @classmethod
    def get_name(cls):
        return cls.name

    @classmethod
    def get_path(cls):
        return f'{cls.__module__}.{cls.__qualname__}'

    @classmethod
    def delay(cls, *args, **kwargs):
        """
        This method is called in the application context
        """
        # try to extract the name
        name = kwargs.pop('name', None)
        # try to extract the passed file
        fp = kwargs.pop('fp', None)
        # try to extract the environment dictionary
        envs = kwargs.pop('envs', None)
        # try to get the task author
        author = kwargs.pop('author', None)

        # create a task with a unique id
        task = apps.get_model('bg.Task').objects.create(
            name=name or cls.get_name(),
            cls_path=cls.get_path(),
            phase='draft',
            phases_history=[],
            args=args,
            kwargs=kwargs,
            envs=envs,
            author=author,
        )
        if fp:
            task.file.save(fp.name, fp)

        # start the task
        task.state = 'waiting'
        task.phase = 'waiting for start'
        task.save()

        return task

    @classmethod
    def delay_sync(cls, *args, **kwargs):
        """
        Starts and waits for completion
        """
        task = cls.delay(*args, **kwargs)
        # wait for completion
        while not apps.get_model('bg.Task').objects.get(id=task.id).state == 'done':
            sleep(1)
        return task

    @classmethod
    def run(cls, task, *args, **kwargs): # noqa [C901]
        """
        This method is called in the context of a separate process
        """
        error = None
        obj = None
        # the log of the task collects all records logged while it runs; the handler is
        # removed afterwards, since a handler process runs many tasks one after another
        root_logger = logging.getLogger()
        root_level = root_logger.level
        log_handler = None

        try:
            obj = cls(*args, **kwargs)

            obj.task_id = task.id
            obj.task_name = task.name
            # start of the phase
            obj._start = None
            # phase name
            obj._phase_name = None
            # timestamp of the last update
            obj._last_sync = None
            # counter
            obj._i = None
            # actual expected progress
            obj._expected = None
            # actual performed progress
            obj._performed = None
            # create a logger specifically for the given task
            obj._log = StringIO()
            obj.log = root_logger
            if root_level == logging.NOTSET or root_level > logging.INFO:
                root_logger.setLevel(logging.INFO)
            log_handler = BgLogHandler(obj._log)
            root_logger.addHandler(log_handler)

            # disable autocommit
            if cls.is_transaction:
                set_autocommit(False)

            # run the main class logic
            try:
                obj.pre_handle()
                obj.handle()
                obj.post_handle()
            except Exception:  # NOQA [B902]
                # roll back
                if cls.is_transaction:
                    rollback()
                raise
            else:
                if cls.is_transaction:
                    commit()
            finally:
                # enable autocommit
                if cls.is_transaction:
                    set_autocommit(True)
        except InterruptException:
            phase = 'interrupted'
            # allow the child class to properly handle interruption
            if obj:
                try:
                    obj.interrupting()
                except Exception:  # NOQA [B902]
                    LOG.fatal(
                        'Interrupting error in class (%s, %s): %s',
                        cls.__name__,
                        task.id,
                        traceback.format_exc(),
                    )
        except Exception:  # NOQA [B902]
            phase = 'error'
            error = traceback.format_exc()
            LOG.fatal('Exception in class (%s, %s): %s', cls.__name__, task.id, error)
            # allow the child class to properly handle the exception
            if obj:
                try:
                    obj.excepting()
                except Exception:  # NOQA [B902]
                    LOG.fatal(
                        'Excepting error in class (%s, %s): %s',
                        cls.__name__,
                        task.id,
                        traceback.format_exc(),
                    )
        else:
            phase = 'completed'
        finally:
            if obj:
                # save the last state of the phase
                try:
                    obj._phase_save()
                except Exception:  # NOQA [B902]
                    LOG.error(
                        'Finish _phase_save error in class (%s, %s): %s',
                        cls.__name__,
                        task.id,
                        traceback.format_exc(),
                    )

                # allow child class to correctly handle unconditional completion
                try:
                    obj.finishing()
                except Exception:  # NOQA [B902]
                    LOG.fatal(
                        'Finishing error in class (%s, %s): %s',
                        cls.__name__,
                        task.id,
                        traceback.format_exc(),
                    )
            if log_handler is not None:
                root_logger.removeHandler(log_handler)
                root_logger.setLevel(root_level)

        # get the task for completion
        task = apps.get_model('bg.Task').objects.get(id=task.id)
        task.set_done(phase, error)

    def interrupting(self):
        pass

    def excepting(self):
        pass

    def finishing(self):
        pass

    def set_result(self, result):
        self.task_update(result=result)

    def get_task(self):
        return apps.get_model('bg.Task').objects.get(id=self.task_id)

    def task_update(self, **kwargs):
        # commit to synchronize the DB
        if self.is_transaction:
            commit()

        # simple update
        task = self.get_task()
        for k, v in kwargs.items():
            setattr(task, k, v)

        # perform a real update only when there is data
        if kwargs:
            task.save(update_fields=kwargs.keys())

        # check whether the task has been interrupted
        if task.interrupt:
            self.log.warning('The task was interrupted!')
            raise InterruptException

        # commit
        if self.is_transaction:
            commit()

        # return the task object
        return task

    def task_file_save(self, name: str, fp: BufferedIOBase, file_params: dict = None):
        """
        Saves a file in the task object.

        :param name: File name
        :param fp: file descriptor
        :param file_params: dictionary of additional file data
        """
        # save the file
        task = self.get_task()
        task.file.save(name, fp)
        if file_params:
            return self.task_update(file_params=file_params)
        return task

    def task_file_get(self) -> BufferedIOBase | None:
        """
        Returns the saved file descriptor from the task
        """
        task = self.get_task()
        return task.file.file if task.file else None

    def next_phase(self, phase_name: str, expected: int | dict[str, int] = None):
        """
        Sets a new task phase

        :param phase_name: String name of the phase
        :param expected: expected number of operations. Can be a dictionary
        :return:
        """
        # save the last status state
        self._phase_save()

        self.task_update(phase=phase_name, expected=expected)
        self.log.info('%s. Expected count: %s', phase_name, expected or 'not defined')

        # initialize phase variables
        self._phase_name = phase_name
        self._start = now()
        self._last_sync = time()
        self._i = 0
        self._expected = expected
        self._performed = None

    def flush(self):
        """
        Synchronizes data with the DB
        """
        # update progress and optionally change the expected number of operations
        self.task_update(
            performed=self._performed,
            expected=self._expected,
            log=self._log.getvalue(),
        )
        # update the last synchronization time
        self._last_sync = time()

    def progress(
        self,
        performed: int | dict[str, int] = None,
        expected: int | dict[str, int] = None,
        d_time: int = None,
        d_count: int = None,
        need_sync: bool = False,
    ):
        """
        Sets the execution and expectation counters.
        Checks and synchronizes data with the DB

        :param performed: current number of completed operations. Can be a dictionary
        :param expected: expected number of operations. Can be a dictionary
        :param d_time: synchronization period, seconds
        :param d_count: if set, also limits the synchronization period by the number of operations
        :param need_sync: if True, forces synchronization with the DB
        :return:
        """
        # increase counter
        self._i += 1
        # save actual progress
        self._performed = performed if performed is not None else self._i
        # save actual expectation
        if expected:
            self._expected = expected

        # 3 seconds - default synchronization period
        d_time = d_time or 3

        # always decide based on d_time. If d_count is set, it also limits the time checks
        if not need_sync and (not d_count or (self._i % d_count) == 0):
            need_sync = (time() - self._last_sync) > d_time

        if need_sync:
            self.flush()

    def pre_handle(self):
        pass

    def handle(self):
        raise Exception('handle no implement!')

    def post_handle(self):
        pass

    def _phase_save(self):
        """
        Save the status to history along with its execution time
        """
        task = self.get_task()
        task.log = self._log.getvalue()

        if self._start:
            task.performed = None
            task.expected = None
            task.phases_history.append(
                {
                    'phase': self._phase_name,
                    'duration': round((now() - self._start).total_seconds(), 1),
                    'expected': self._expected,
                    'performed': self._performed,
                }
            )
            self.log.info('Phase recorded: %s', self._phase_name)

        task.save(update_fields=['performed', 'expected', 'phases_history', 'log'])
        # commit
        if self.is_transaction:
            commit()
