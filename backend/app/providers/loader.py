"""Import every provider module so its ``register(...)`` call runs.

Import this module once at startup (``app.main``) to populate the registry.
"""

from __future__ import annotations

from app.providers import alpaca as _alpaca  # noqa: F401
from app.providers import fred as _fred  # noqa: F401
from app.providers import openai_provider as _openai  # noqa: F401
