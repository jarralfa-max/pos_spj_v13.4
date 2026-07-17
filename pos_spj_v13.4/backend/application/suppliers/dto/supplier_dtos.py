"""Supplier DTOs — plain, display-ready structures returned by query services."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SupplierListItemDTO:
    supplier_id: str          # UUID (hidden in UI, used for actions)
    code: str
    name: str
    tax_identifier: str
    status: str
    rating_grade: str | None
    risk_level: str | None
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class SupplierDetailDTO:
    supplier_id: str
    code: str
    legal_name: str
    trade_name: str
    tax_identifier: str
    status: str
    rating_grade: str | None
    risk_level: str | None
    preferred_currency: str
    classifications: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    active_blocks: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class SupplierDashboardDTO:
    active_suppliers: int
    pending_approval: int
    blocked: int
    payable_balance: str
    overdue_balance: str
    documents_expiring: int


@dataclass(frozen=True)
class SupplierEvaluationDTO:
    supplier_id: str
    period: str
    score: int
    rating_grade: str | None
    items: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class SupplierRiskDTO:
    supplier_id: str
    level: str
    causes: tuple[str, ...] = ()
