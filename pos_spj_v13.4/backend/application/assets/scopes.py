"""Data scopes for the Assets/EAM bounded context (§83).

A permission says *whether* a user may act; a scope says *which rows* they
may see/act on. A custodian sees their own assigned assets, a technician sees
work orders assigned to them, a branch manager sees their branch, an asset
manager sees the company, an auditor sees an authorized global read.

QueryServices/UseCases built in later ASSET phases take an ``AssetDataScope``
alongside the permission check rather than trusting a caller-supplied branch
filter — the resolver is the single place that turns "this user, this
permission" into "these branch_ids / this custodian_id".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class AssetScopeLevel(str, Enum):
    OWN = "OWN"
    ASSIGNED = "ASSIGNED"
    BRANCH = "BRANCH"
    REGION = "REGION"
    COMPANY = "COMPANY"
    ALL = "ALL"


@dataclass(frozen=True, slots=True)
class AssetDataScope:
    """Resolved scope for one user/permission pair.

    ``branch_ids``/``custodian_user_id`` are populated only for the scope
    levels that need them (BRANCH/REGION → branch_ids, OWN/ASSIGNED →
    custodian_user_id); COMPANY/ALL leave both unset (no filter applied).
    """

    level: AssetScopeLevel
    branch_ids: tuple[str, ...] = ()
    custodian_user_id: str | None = None


class AssetDataScopeResolver(Protocol):
    """Resolves the data scope a user is authorized to see for a given
    permission code. Concrete implementation lands with the QueryServices
    (ASSET-14) — this is the contract other phases build against."""

    def resolve(self, user_id: str, permission_code: str) -> AssetDataScope: ...
