try:
    from importlib.metadata import PackageNotFoundError, version
    __version__ = version('bazis-bg')
except PackageNotFoundError:
    __version__ = 'dev'


REGISTRY_BG_TASKS = {}
