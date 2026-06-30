"""API route modules for llm-apipool proxy.

Each module exposes a factory function ``_create_*_router`` that accepts
shared dependencies (store, rotator, configs) and returns a configured
``APIRouter`` instance.
"""

from __future__ import annotations


from . import analytics
from . import anthropic
from . import benchmark
from . import bulk_import
from . import chat
from . import effort
from . import embeddings
from . import freemodels
from . import health
from . import keys
from . import logs
from . import media
from . import models
from . import responses
from . import settings
from . import tiers

__all__ = [
    "analytics",
    "anthropic",
    "benchmark",
    "bulk_import",
    "chat",
    "effort",
    "embeddings",
    "freemodels",
    "health",
    "keys",
    "logs",
    "media",
    "models",
    "responses",
    "settings",
    "tiers",
]
