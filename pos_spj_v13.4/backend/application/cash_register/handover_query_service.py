"""Read model for CASH-16 value handovers."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


class HandoverReader(Protocol):
    def list_for_branch(self, *, branch_id: str, limit: int = 100) -> list[dict]: ...
    def list_denominations(self, handover_id: str) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class CashHandoverRow:
    id: str
    shift_id: str
    amount: Decimal | None
    status: str
    prepared_by: str
    delivered_by: str
    received_by: str
    prepared_at: str
    delivered_at: str
    received_at: str
    dispute_reason: str
    #: Nombres para la pantalla (auditoría CJA-05): nunca el id del usuario.
    prepared_by_name: str = ""
    delivered_by_name: str = ""
    received_by_name: str = ""


class CashHandoverQueryService:
    """Auditoría de Caja (cierre de pendientes, 2026-10-16): con `authorization`
    (la composición real la inyecta) la lista exige usuario y `CAJA.entrega.ver`
    en la sucursal, y el MONTO sólo lo ve quien preparó la entrega, quien la
    recibe (`CAJA.entrega.recibir`) o quien tiene importes sensibles. Antes no
    recibía usuario y entregaba montos e ids a cualquier pantalla."""

    def __init__(self, reader: HandoverReader, *, connection=None, authorization=None) -> None:
        self._reader = reader
        self._conn = connection
        self._auth = authorization

    def _names(self, ids: set[str]) -> dict[str, str]:
        ids = {i for i in ids if i}
        if not ids or self._conn is None:
            return {}
        marks = ",".join("?" for _ in ids)
        try:
            return {str(r[0]): str(r[1] or "") for r in self._conn.execute(
                "SELECT id, COALESCE(NULLIF(trim(nombre),''), usuario) FROM usuarios"
                f" WHERE id IN ({marks})", tuple(ids))}
        except Exception:  # noqa: BLE001 - base sin usuarios legibles
            return {}

    def list_for_branch(self, branch_id: str, *,
                        requester_user_id: str | None = None) -> tuple[CashHandoverRow, ...]:
        if not str(branch_id or "").strip():
            return ()
        sees_all = True
        if self._auth is not None:
            from backend.application.cash_register.permissions import CashPermissions
            self._auth.require(user_id=requester_user_id or "",
                               permission_code=CashPermissions.HANDOVER_VIEW,
                               branch_id=branch_id)
            sees_all = any(self._auth.has_permission(
                user_id=requester_user_id or "", permission_code=code, branch_id=branch_id)
                for code in (CashPermissions.VIEW_SENSITIVE_AMOUNTS,
                             CashPermissions.HANDOVER_RECEIVE))
        records = list(self._reader.list_for_branch(branch_id=branch_id))
        names = self._names({str(r.get(k) or "") for r in records
                             for k in ("prepared_by", "delivered_by", "received_by")})
        return tuple(
            CashHandoverRow(
                id=str(row["id"]),
                shift_id=str(row["shift_id"]),
                amount=(Decimal(str(row["amount"]))
                        if sees_all or str(row.get("prepared_by") or "") == requester_user_id
                        else None),
                status=str(row["status"]),
                prepared_by=str(row.get("prepared_by") or ""),
                delivered_by=str(row.get("delivered_by") or ""),
                received_by=str(row.get("received_by") or ""),
                prepared_at=str(row.get("prepared_at") or ""),
                delivered_at=str(row.get("delivered_at") or ""),
                received_at=str(row.get("received_at") or ""),
                dispute_reason=str(row.get("dispute_reason") or ""),
                prepared_by_name=names.get(str(row.get("prepared_by") or ""), ""),
                delivered_by_name=names.get(str(row.get("delivered_by") or ""), ""),
                received_by_name=names.get(str(row.get("received_by") or ""), ""),
            )
            for row in records
        )

    def denomination_quantities(self, handover_id: str) -> dict[str, int]:
        return {
            str(row["denomination_id"]): int(row["quantity"])
            for row in self._reader.list_denominations(handover_id)
        }
