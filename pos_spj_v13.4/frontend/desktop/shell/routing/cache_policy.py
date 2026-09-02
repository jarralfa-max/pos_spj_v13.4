"""CachePolicy — SHELL-9 §53.

Governs whether `ContentHost` (SHELL-11) keeps a route's constructed view
around across navigation or throws it away. Enforcing this is
`ContentHost`'s job once it exists — this is only the declarative value a
`RouteDefinition` carries.
"""
from __future__ import annotations

from enum import Enum


class CachePolicy(str, Enum):
    KEEP_ALIVE = "KEEP_ALIVE"
    RECREATE_ON_NAVIGATION = "RECREATE_ON_NAVIGATION"
    RECREATE_ON_CONTEXT_CHANGE = "RECREATE_ON_CONTEXT_CHANGE"
    SINGLETON = "SINGLETON"
