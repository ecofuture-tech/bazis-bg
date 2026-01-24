from django.core.exceptions import FieldDoesNotExist

from ..basic.base_download import BgBaseDownload


class BgBaseDownloadModel(BgBaseDownload):
    model = None

    @classmethod
    def get_name(cls):
        return f'Export: {cls.model._meta.verbose_name}'

    def get_titles(self):
        fields = {}
        for k in self.fields_read:
            try:
                fields[k] = self.model._meta.get_field(k).verbose_name
            except FieldDoesNotExist:
                fields[k] = k
        return fields

    def __init__(self):
        self.qs = self.model.objects.all()
        self.file_name = self.model.get_resource_name()

    def get_queryset(self):
        return self.qs

    def get_count(self):
        return self.qs.count()
