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


class XlsxReader:

    def __init__(self, fp, file_params):
        self.fp = fp
        self.fields_read = file_params.get('fields', [])
        self.titles = file_params.get('titles', {})
        self.groups_check = file_params.get('groups_check', False)
        self.files = None
        self.tmp_folder = None
        self.wb = None
        self.count = 0
        self.total_count = file_params.get('total_count', 0)

        if not self.titles:
            self.count_title_rows = 0
        elif 'groups' in self.titles and isinstance(self.titles['groups'], list):
            self.count_title_rows = 2
        else:
            self.count_title_rows = 1

    def event(self, e_type, *args, **kwargs):
        pass

    def get_titles(self):
        if not self.count_title_rows:
            return {f_name: f_name for f_name in self.fields_read}
        elif self.count_title_rows == 2:
            groups = self.titles['groups']
            titles = self.titles['titles']
            items = {}
            for f_name in self.fields_read:
                # find the group for the current column
                group = ([group for group in groups if f_name in group['columns']] + [None])[0]
                if group:
                    items[f_name] = group['name_unit'] % titles[f_name]
                else:
                    items[f_name] = titles[f_name]
            return items
        else:
            return {f_name: self.titles[f_name] for f_name in self.fields_read}

    def get_count(self):
        return self.count

    def __enter__(self):
        # determine the file extension
        ext = os.path.splitext(os.path.split(self.fp.name)[-1])[-1]

        if ext == '.xlsx':
            self.files = [self.fp.name]
        elif ext == '.zip':
            # in archive mode, groups cannot be processed
            self.groups_check = False
            # create a temporary folder
            self.tmp_folder = tempfile.mkdtemp()
            # extract the archive there
            with ZipFile(self.fp) as zp:
                zp.extractall(self.tmp_folder)
            # get the list of paths
            self.files = [os.path.join(self.tmp_folder, fn) for fn in os.listdir(self.tmp_folder)]
            self.event('zip', self.files)
        else:
            raise Exception('Unsupported file extension for upload')
        return self

    def __getitem__(self, key):
        result = None
        if isinstance(key, slice):
            result = []
            start = key.start
            stop = key.stop
            for i, it in enumerate(iter(self)):
                if i < start:
                    continue
                if i >= stop:
                    break
                result.append(it)
        else:
            for i, it in enumerate(iter(self)):
                if i == key:
                    result = it
        return result

    def __len__(self):
        return self.total_count

    def __iter__(self):
        fields_read = self.fields_read

        for f_path in self.files:
            # load the file
            self.wb = load_workbook(f_path, read_only=not self.groups_check, data_only=True)
            ws = self.wb.active
            count = (ws.max_row - self.count_title_rows) if ws.max_row else 0
            self.count += count

            self.event('file_read', f_path, count)

            row_num = 0
            rows = ws.iter_rows(values_only=True)
            # header row
            if self.count_title_rows:
                row_num += self.count_title_rows
                [next(rows) for _ in range(self.count_title_rows)]

            # if tracking groups is enabled, request them
            groups = ws.row_dimensions if self.groups_check else {}

            for row in rows:
                # skip completely empty rows
                if all([not col for col in row]):
                    continue

                row_num += 1

                row = (list(row) + ([None] * len(fields_read)))[: len(fields_read)]
                # main values
                data = dict(
                    zip(
                        [field for i, field in enumerate(fields_read)],
                        [val for j, val in enumerate(row)], strict=False,
                    )
                )
                # everything beyond the header length is loaded into a special key
                if len(fields_read) < len(row):
                    data['_ext'] = row[len(fields_read) :]
                # row metadata
                data['_meta'] = {'row_num': row_num}
                # if there are groups, get the nesting level
                if row_num in groups:
                    data['_meta']['group_level'] = groups.get(row_num).outline_level
                yield data
                self.event('row')
            self.wb.close()
            self.wb = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.wb:
            self.wb.close()

        # if a temporary folder was created, delete it
        if self.tmp_folder:
            shutil.rmtree(self.tmp_folder)
