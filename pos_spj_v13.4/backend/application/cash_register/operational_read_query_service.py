"""Read-only operational sections for CASH-23 Caja UI pages.

This service intentionally exposes compact rows for secondary operational pages
whose source of truth already exists in Caja. The desktop UI consumes this
service through the presenter; it never imports repositories or executes SQL.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions


@dataclass(frozen=True, slots=True)
class CashOperationalReadRow:
    id: str
    primary: str
    secondary: str
    status: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class CashOperationalReadSection:
    key: str
    title: str
    rows: tuple[CashOperationalReadRow, ...]


class CashOperationalReadQueryService:
    """Read model for real CASH-23 pages backed by born-clean Caja tables."""

    _SECTIONS: dict[str, tuple[str, str, str, tuple[str, ...]]] = {
        "deposits": (
            "Depositos preparados",
            CashPermissions.DEPOSIT_VIEW,
            """SELECT id,event_name,entity_id,'PREPARED',occurred_at
               FROM cash_domain_events
               WHERE branch_id=? AND event_name='CASH_DEPOSIT_PREPARED'
               ORDER BY occurred_at DESC LIMIT ?""",
            (),
        ),
        "payment_methods": (
            "Medios de pago",
            CashPermissions.PAYMENT_METHOD_VIEW,
            """SELECT id,display_name,code,
                      CASE active WHEN 1 THEN 'ACTIVO' ELSE 'INACTIVO' END,
                      effective_from
               FROM cash_payment_methods
               ORDER BY active DESC,code LIMIT ?""",
            ("global",),
        ),
        "payment_terminals": (
            "Terminales de pago",
            CashPermissions.PAYMENT_TERMINAL_VIEW,
            """SELECT id,name,register_id,status,updated_at
               FROM pos_terminals
               WHERE branch_id=?
               ORDER BY updated_at DESC LIMIT ?""",
            (),
        ),
        "drawer_events": (
            "Eventos de cajon",
            CashPermissions.DRAWER_EVENT_VIEW,
            """SELECT id,event_name,entity_id,'AUDITADO',occurred_at
               FROM cash_domain_events
               WHERE branch_id=? AND event_name='CASH_DRAWER_OPENED'
               ORDER BY occurred_at DESC LIMIT ?""",
            (),
        ),
        "audit": (
            "Auditoria",
            CashPermissions.AUDIT_VIEW,
            """SELECT id,action,entity_id,COALESCE(reason,''),occurred_at
               FROM cash_audit_log
               WHERE branch_id=?
               ORDER BY occurred_at DESC LIMIT ?""",
            (),
        ),
    }

    def __init__(self, connection, authorization: CashAuthorizationPolicy) -> None:
        self._connection = connection
        self._authorization = authorization

    def section(
        self,
        *,
        section_key: str,
        branch_id: str,
        requester_user_id: str,
        limit: int = 100,
    ) -> CashOperationalReadSection:
        if section_key not in self._SECTIONS:
            raise ValueError(f"Seccion operativa de Caja desconocida: {section_key}")
        title, permission, sql, flags = self._SECTIONS[section_key]
        self._authorization.require(
            user_id=requester_user_id,
            permission_code=permission,
            branch_id=None if "global" in flags else branch_id,
        )
        safe_limit = max(1, min(int(limit or 100), 500))
        params = (safe_limit,) if "global" in flags else (branch_id, safe_limit)
        rows = tuple(
            CashOperationalReadRow(
                id=str(row[0]),
                primary=str(row[1] or ""),
                secondary=str(row[2] or ""),
                status=str(row[3] or ""),
                occurred_at=str(row[4] or ""),
            )
            for row in self._connection.execute(sql, params).fetchall()
        )
        return CashOperationalReadSection(key=section_key, title=title, rows=rows)

