"""Permission-aware CASH-13 X-cut document projection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.blind_count_visibility import shift_has_open_blind_count
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.exceptions import CashInvalidStateError
from backend.infrastructure.db.repositories.cash_register.repositories import CashCutRepository


@dataclass(frozen=True, slots=True)
class XCutDocumentDTO:
    id: str
    document_number: str
    shift_id: str
    generated_at: str
    generated_by: str
    expected_cash: Decimal | None
    snapshot: dict[str, str] | None
    sensitive_amounts_visible: bool
    final: bool = False


class XCutQueryService:
    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._connection = connection
        self._cuts, self._auth = CashCutRepository(connection), authorization

    def list_for_branch(self, *, branch_id: str,
                        requester_user_id: str) -> tuple[XCutDocumentDTO, ...]:
        self._auth.require(user_id=requester_user_id,
                           permission_code=CashPermissions.X_CUT_VIEW,
                           branch_id=branch_id)
        sensitive_allowed = self._auth.has_permission(
            user_id=requester_user_id,
            permission_code=CashPermissions.VIEW_SENSITIVE_AMOUNTS,
            branch_id=branch_id)
        return tuple(
            _dto(
                cut,
                sensitive_amounts_visible=(
                    sensitive_allowed
                    and not shift_has_open_blind_count(self._connection, str(cut["shift_id"]))
                ),
            )
            for cut in self._cuts.list_x_for_branch(branch_id=branch_id)
        )

    def get(self, *, cut_id: str, branch_id: str,
            requester_user_id: str) -> XCutDocumentDTO:
        self._auth.require(user_id=requester_user_id,
                           permission_code=CashPermissions.X_CUT_VIEW,
                           branch_id=branch_id)
        cut = self._cuts.get(cut_id)
        if not cut or cut["branch_id"] != branch_id or cut["cut_type"] != "X":
            raise CashInvalidStateError("Corte X no encontrado en la sucursal")
        visible = self._auth.has_permission(
            user_id=requester_user_id,
            permission_code=CashPermissions.VIEW_SENSITIVE_AMOUNTS,
            branch_id=branch_id)
        if shift_has_open_blind_count(self._connection, str(cut["shift_id"])):
            visible = False
        return _dto(cut, sensitive_amounts_visible=visible)


def _dto(cut: dict, *, sensitive_amounts_visible: bool) -> XCutDocumentDTO:
    return XCutDocumentDTO(
        id=str(cut["id"]),
        document_number=str(cut["document_number"]),
        shift_id=str(cut["shift_id"]),
        generated_at=str(cut["generated_at"]),
        generated_by=str(cut["generated_by"]),
        expected_cash=Decimal(str(cut["expected_cash"])) if sensitive_amounts_visible else None,
        snapshot=json.loads(cut["snapshot_json"]) if sensitive_amounts_visible else None,
        sensitive_amounts_visible=sensitive_amounts_visible,
    )
