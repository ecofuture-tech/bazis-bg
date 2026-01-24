
from pydantic import Field

from bazis.core.utils.schemas import BazisSettings


class Settings(BazisSettings):
    BAZIS_STORAGE_BG: str = Field('', title='Background task file storage engine')
    BAZIS_TASK_FOLDER: str = Field(
        'bg', title='Directory in the application where background tasks are located'
    )
    BAZIS_TASK_HANDLERS_LOCAL: int = Field(5, title='Minimum local number of handlers')
    BAZIS_TASK_HANDLERS_GLOBAL: int = Field(50, title='Global number of handlers')
    BAZIS_TASK_HANDLER_PORT: int = Field(49100, title='Default handler port')
    BAZIS_TASK_HANDLER_IDLE: float = Field(
        0.5, title='Handler wait time before a new work cycle'
    )
    BAZIS_TASK_SCHEDULER_IDLE: float = Field(
        0.2, title='Scheduler wait time before a new work cycle'
    )
    BAZIS_TASK_SCHEDULER_HOST: str | None = Field(None, title='Explicitly specifies the scheduler host')
    BAZIS_TASK_SCHEDULER_PORT: int = Field(49001, title='Default scheduler port')
    BAZIS_TASK_LIFETIME: int = Field(
        7776000, title='Lifetime of manual background tasks', dynamic=True
    )
    BAZIS_TASK_CRON_LIFETIME: int = Field(
        21600, title='Lifetime of periodic background tasks', dynamic=True
    )
    BAZIS_TASK_CRON_CLEANUP: int = Field(
        3600, title='Interval for running cleanup of periodic background tasks', dynamic=True
    )



settings = Settings()
