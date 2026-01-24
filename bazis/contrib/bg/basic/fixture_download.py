import json
from io import BytesIO, StringIO

from django.core.management import call_command
from django.db.models import Model
from django.utils.timezone import now

from bazis.contrib.bg.basic.base import BgBase


class FixtureDownload(BgBase):
    name = 'Fixture export'
    parallel = 1
    models_export: list[type[Model] | str] = []
    file_name = 'fixtures'

    def handle(self):
        models_export = [
            m if isinstance(m, str) else f'{m._meta.app_label}.{m._meta.model_name}'
            for m in self.models_export
        ]

        target_models = ", ".join(models_export)
        self.next_phase(f'Downloading fixtures for models: {target_models}'[:512])

        fp = StringIO()
        call_command(
            'dumpdata',
            *models_export,
            natural_foreign=True,
            natural_primary=True,
            stdout=fp,
        )
        fp.seek(0)

        data = json.load(fp)
        fp = BytesIO()
        fp.write(json.dumps(data, ensure_ascii=False).encode())

        self.task_file_save(f"{now().strftime('%Y-%m-%d_%H-%M-%S')}.{self.file_name}.json", fp)
