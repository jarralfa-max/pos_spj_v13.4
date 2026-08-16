"""CASH-14 permission-aware final Z cut projection."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.repositories import CashCutRepository


@dataclass(frozen=True, slots=True)
class CashZCutDTO:
    id: str
    shift_id: str
    branch_id: str
    document_number: str
    expected_cash: Decimal | None
    counted_cash: Decimal | None
    difference: Decimal | None
    blind_count_id: str
    generated_by: str
    generated_at: str
    is_final: bool
    snapshot: dict[str, str] | None
    sensitive_amounts_visible: bool


class CashZCutQueryService:
    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._repo = CashCutRepository(connection)
        self._auth = authorization

    def get(self, *, cut_id: str, branch_id: str,
            requester_user_id: str) -> CashZCutDTO:
        self._auth.require(
            user_id=requester_user_id,
            permission_code=CashPermissions.Z_CUT_VIEW,
            branch_id=branch_id,
        )
        row = self._repo.get(cut_id)
        if not row or row["branch_id"] != branch_id or row["cut_type"] != "Z":
            raise CashInvalidStateError("Corte Z no encontrado en la sucursal")
        return _dto(
            row,
            sensitive_amounts_visible=self._can_view_sensitive_amounts(
                requester_user_id=requester_user_id,
                branch_id=branch_id,
            ),
        )

    def list_for_branch(self, *, branch_id: str,
                        requester_user_id: str) -> tuple[CashZCutDTO, ...]:
        self._auth.require(
            user_id=requester_user_id,
            permission_code=CashPermissions.Z_CUT_VIEW,
            branch_id=branch_id,
        )
        visible = self._can_view_sensitive_amounts(
            requester_user_id=requester_user_id,
            branch_id=branch_id,
        )
        return tuple(
            _dto(row, sensitive_amounts_visible=visible)
            for row in self._repo.list_z_for_branch(branch_id=branch_id)
        )

    def _can_view_sensitive_amounts(self, *, requester_user_id: str,
                                    branch_id: str) -> bool:
        return self._auth.has_permission(
            user_id=requester_user_id,
            permission_code=CashPermissions.VIEW_SENSITIVE_AMOUNTS,
            branch_id=branch_id,
        )


def _dto(row: dict, *, sensitive_amounts_visible: bool) -> CashZCutDTO:
    return CashZCutDTO(
        id=str(row["id"]),
        shift_id=str(row["shift_id"]),
        branch_id=str(row["branch_id"]),
        document_number=str(row["document_number"]),
        expected_cash=(
            Decimal(str(row["expected_cash"] or "0"))
            if sensitive_amounts_visible else None
        ),
        counted_cash=(
            Decimal(str(row["counted_cash"] or "0"))
            if sensitive_amounts_visible else None
        ),
        difference=(
            Decimal(str(row["difference"] or "0"))
            if sensitive_amounts_visible else None
        ),
        blind_count_id=str(row.get("blind_count_id") or ""),
        generated_by=str(row["generated_by"]),
        generated_at=str(row["generated_at"]),
        is_final=bool(row["is_final"]),
        snapshot=(
            json.loads(row["snapshot_json"])
            if sensitive_amounts_visible and row.get("snapshot_json")
            else None
        ),
        sensitive_amounts_visible=sensitive_amounts_visible,
    )
