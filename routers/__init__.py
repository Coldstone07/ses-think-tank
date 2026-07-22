"""
Router modules for SES Think Tank.

Each domain has its own APIRouter. app.py includes them all.
"""
from .core import router as core_router
from .plugins import router as plugins_router
from .intelligence import router as intelligence_router
from .auth import router as auth_router
from .sessions import router as sessions_router
from .research import router as research_router
from .collaboration import router as collaboration_router
from .platform import router as platform_router

__all__ = [
    "core_router",
    "plugins_router",
    "intelligence_router",
    "auth_router",
    "sessions_router",
    "research_router",
    "collaboration_router",
    "platform_router",
]
