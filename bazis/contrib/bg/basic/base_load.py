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

import os
import shutil
import tempfile
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils.cell import get_column_letter

from .base import BgBase


class BgBaseLoad(BgBase):
    fields_read = []
    skip_titles = False
    progress_count = 1000
    groups_check = False
    with_meta = False
    tmp_folder = None
    tmp_file = None

    def handle(self):
        # get the file
        fp = self.task_file_get()
        if not fp:
            raise Exception('File not provided!')

        # determine the file extension
        ext = os.path.splitext(os.path.split(fp.name)[-1])[-1]

        # create a temporary local file, since the file may be taken from S3
        self.tmp_file = tempfile.NamedTemporaryFile(suffix=ext)
        shutil.copyfileobj(fp, self.tmp_file)
        self.tmp_file.seek(0)

        if ext == '.xlsx':
            files = [self.tmp_file.name]
            self.log.info('Received xlsx file: %s', fp.name)
        elif ext == '.zip':
            # in archive mode, groups cannot be processed
            self.groups_check = False
            # create a temporary folder
            self.tmp_folder = tempfile.mkdtemp()
            # extract the archive there
            with ZipFile(self.tmp_file) as zp:
                zp.extractall(self.tmp_folder)
            # get the list of paths (without the metadata that macOS adds to archives)
            files = sorted(
                os.path.join(root, fn)
                for root, _dirs, fns in os.walk(self.tmp_folder)
                if '__MACOSX' not in os.path.relpath(root, self.tmp_folder).split(os.sep)
                for fn in fns
                if fn.endswith('.xlsx') and not fn.startswith('._')
            )
            self.log.info('Received zip archive: %s', ', '.join(files))
        else:
            raise Exception('Unsupported file extension for upload')

        def reader():
            for f_path in files:
                # load the file
                wb = load_workbook(f_path, read_only=not self.groups_check, data_only=True)
                ws = wb.active
                count = (ws.max_row - int(self.skip_titles)) if ws.max_row else 0
                fields_read = self.fields_read

                self.next_phase(f'Reading file {f_path}', count)

                row_num = 0
                rows = ws.iter_rows(values_only=True)
                # header row
                if self.skip_titles:
                    heads = (list(next(rows)) + ([None] * len(fields_read)))[: len(fields_read)]
                    row_num += 1
                else:
                    heads = [get_column_letter(i + 1) for i in range(len(fields_read))]

                # if group tracking is enabled, request them
                groups = ws.row_dimensions if self.groups_check else {}

                for row in rows:
                    # skip completely empty row
                    if all([not col for col in row]):
                        continue

                    row_num += 1

                    row = (list(row) + ([None] * len(fields_read)))[: len(fields_read)]
                    # main values
                    data = dict(
                        zip(
                            [field for i, field in enumerate(fields_read) if heads[i]],
                            [val for j, val in enumerate(row) if heads[j]], strict=False,
                        )
                    )
                    # everything beyond the header length is loaded into a special key
                    if len(fields_read) < len(row):
                        data['_ext'] = row[len(fields_read) :]
                    # row metadata
                    if self.with_meta:
                        data['_meta'] = {
                            'row_num': row_num,
                        }
                        # if there are groups, get nesting
                        if row_num in groups:
                            data['_meta']['group_level'] = groups.get(row_num).outline_level
                    yield data
                    self.progress(d_count=self.progress_count)
                wb.close()

        self.load(reader())

    def load(self, reader):
        return

    def finishing(self):
        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)
        if self.tmp_file:
            self.tmp_file.close()
