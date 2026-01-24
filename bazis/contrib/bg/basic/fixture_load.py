import tempfile

from django.core.management import call_command
from django.db import transaction

from bazis.contrib.bg.basic.base import BgBase


class FixtureLoad(BgBase):
    name = 'Fixture loading'
    parallel = 1
    clear_models = []

    def handle(self):
        with transaction.atomic():
            # clear models
            for model in self.clear_models:
                model.objects.all().delete()

            # get file
            fp = self.task_file_get()

            # create a temporary local file, since the file may be taken from S3
            tmp_fp = tempfile.NamedTemporaryFile(suffix='.json')
            tmp_fp.write(fp.read())
            tmp_fp.seek(0)

            try:
                call_command('loaddata', tmp_fp.name, ignorenonexistent=True)
            finally:
                tmp_fp.close()
