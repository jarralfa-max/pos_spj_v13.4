"""Product lifecycle policy (§10) — the single source of legal state transitions.

A product is created DRAFT, submitted for review, approved, activated, and may
then be blocked/unblocked, deactivated/reactivated, discontinued and finally
archived. A product with history is never physically deleted (§10, §47). The
entity and the use cases both consult this table so the rule lives in one place.
"""

from __future__ import annotations

from backend.domain.products.enums import LifecycleStatus as S

# origen → destinos permitidos
_TRANSITIONS: dict[S, frozenset[S]] = {
    S.DRAFT: frozenset({S.UNDER_REVIEW, S.ACTIVE, S.INACTIVE, S.ARCHIVED}),
    S.UNDER_REVIEW: frozenset({S.DRAFT, S.ACTIVE, S.INACTIVE, S.ARCHIVED}),
    S.ACTIVE: frozenset({S.BLOCKED, S.INACTIVE, S.DISCONTINUED}),
    S.BLOCKED: frozenset({S.ACTIVE, S.INACTIVE, S.DISCONTINUED}),
    S.INACTIVE: frozenset({S.ACTIVE, S.DISCONTINUED, S.ARCHIVED}),
    S.DISCONTINUED: frozenset({S.ARCHIVED}),
    S.ARCHIVED: frozenset(),
}


def can_transition(current: LifecycleStatus, target: LifecycleStatus) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def allowed_targets(current: LifecycleStatus) -> frozenset[LifecycleStatus]:
    return _TRANSITIONS.get(current, frozenset())


# alias de tipo para anotaciones legibles
LifecycleStatus = S
