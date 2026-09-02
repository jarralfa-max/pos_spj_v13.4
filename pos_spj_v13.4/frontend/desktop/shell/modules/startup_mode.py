"""StartupMode — SHELL-8 §48."""
from __future__ import annotations

from enum import Enum


class StartupMode(str, Enum):
    EAGER = "EAGER"
    LAZY = "LAZY"
    ON_DEMAND = "ON_DEMAND"
    BACKGROUND_PRELOAD = "BACKGROUND_PRELOAD"
