"""Lifetime — SHELL-5 §15.

`_LIFETIME_RANK` encodes how long each lifetime lives, shortest number =
longest-lived. `DependencyGraphValidator` uses it to catch the classic DI
"captive dependency" bug: a longer-lived registration (say, SINGLETON)
depending on a shorter-lived one (say, SESSION) would capture whichever
instance existed the moment the singleton was first built, and hold it
forever — even after that session ends. A dependent may only depend on
services that live at least as long as it does (`rank[dependent] >=
rank[dependency]`).

SINGLETON and APPLICATION resolve identically (one instance per
`ServiceContainer`, cached forever) — they're kept as distinct enum values
because the master plan names both, not because the resolution mechanics
differ; the distinction is intent (framework-level singleton vs.
this-running-app singleton), not behavior.
"""
from __future__ import annotations

from enum import Enum


class Lifetime(str, Enum):
    SINGLETON = "SINGLETON"
    APPLICATION = "APPLICATION"
    SESSION = "SESSION"
    OPERATION = "OPERATION"
    VIEW = "VIEW"
    TRANSIENT = "TRANSIENT"


# Lower rank = lives longer. OPERATION and VIEW are siblings (neither may
# depend on the other). TRANSIENT ranks last: never cached, so nothing may
# hold one past the resolve() call that created it without breaking the
# "always fresh" promise.
_LIFETIME_RANK = {
    Lifetime.SINGLETON: 0,
    Lifetime.APPLICATION: 0,
    Lifetime.SESSION: 1,
    Lifetime.OPERATION: 2,
    Lifetime.VIEW: 2,
    Lifetime.TRANSIENT: 3,
}

# The lifetimes a `ServiceScope` can own (SESSION/OPERATION/VIEW are always
# resolved through an explicit scope, never directly off the root container
# — see service_container.py).
SCOPED_LIFETIMES = frozenset({Lifetime.SESSION, Lifetime.OPERATION, Lifetime.VIEW})
ROOT_LIFETIMES = frozenset({Lifetime.SINGLETON, Lifetime.APPLICATION, Lifetime.TRANSIENT})

# Same-rank pairs that are still NOT interchangeable: OPERATION and VIEW sit
# at the same depth but are unrelated scope kinds (a business transaction
# vs. a UI page), so neither may depend on the other even though neither
# outlives the other. SINGLETON/APPLICATION, by contrast, share a rank
# *and* resolve identically — depending across that pair is fine.
_SIBLING_EXCLUSIVE_PAIRS = frozenset({
    frozenset({Lifetime.OPERATION, Lifetime.VIEW}),
})


def rank(lifetime: Lifetime) -> int:
    return _LIFETIME_RANK[lifetime]


def is_lifetime_compatible(*, dependent: Lifetime, dependency: Lifetime) -> bool:
    """True if `dependent` is allowed to depend on `dependency` without a
    captive-dependency hazard.

    Compatible when the dependency is strictly longer-lived (lower rank).
    Equal rank is only compatible when the two lifetimes aren't a declared
    sibling-exclusive pair (see `_SIBLING_EXCLUSIVE_PAIRS`) — same rank
    alone doesn't mean interchangeable.
    """
    if frozenset({dependent, dependency}) in _SIBLING_EXCLUSIVE_PAIRS:
        return False
    return rank(dependency) <= rank(dependent)
