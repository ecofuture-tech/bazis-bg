from django.apps import apps

from bazis.core.apps import BaseConfig
from bazis.core.utils.imp import import_module, pkg_load


class BgConfig(BaseConfig):
    name = 'bazis.contrib.bg'
    verbose_name = 'Background tasks'

    def ready(self):
        super().ready()

        # perform loading of bg packages of connected applications
        for app in apps.get_app_configs():
            try:
                bg_pkg = import_module(f'{app.module.__name__}.bg')
            except ModuleNotFoundError:
                pass
            else:
                pkg_load(bg_pkg)

