"""ShutdownContext — SHELL-15.

The bag passed to every `ShutdownStep.run()`, same role `BootstrapContext`
(SHELL-3) plays for boot steps. Today's three steps (`WorkersShutdownStep`,
`OutboxShutdownStep`, `ConnectionsShutdownStep`) get everything they need
through constructor injection instead — nothing currently reads or writes
this context — but the shape is kept consistent with `BootstrapStep`'s
`run(context)` Protocol so a future step can use `extras` without every
existing step's signature changing. `reason` is a free-form string
(e.g. "USER_REQUESTED", "APPLICATION_UPDATE") a step can log or branch on;
no enum is enforced since nothing in this phase depends on a specific
value existing.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ShutdownContext:
    reason: str = ""
    extras: dict = field(default_factory=dict)
