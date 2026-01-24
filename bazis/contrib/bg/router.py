
from bazis.core.routing import BazisRouter

from .routes import BgRoute


router = BazisRouter(tags=['Background tasks'])
router.register(BgRoute.as_router())
