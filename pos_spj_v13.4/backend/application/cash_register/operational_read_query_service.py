"""Read-only operational sections for CASH-23 Caja UI pages.

This service intentionally exposes compact rows for secondary operational pages
whose source of truth already exists in Caja. The desktop UI consumes this
service through the presenter; it never imports repositories or executes SQL.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.application.cash_register.authorization import CashAuthorizationPolicy
from backend.application.cash_register.permissions import CashPermissions
from backend.domain.cash_register.settlements import settlement_catalog


@dataclass(frozen=True, slots=True)
class CashOperationalReadRow:
    id: str
    primary: str
    secondary: str
    status: str
    occurred_at: str


@dataclass(frozen=True, slots=True)
class CashRefundRow:
    """Un reembolso ya ejecutado, para la página de Reembolsos (CASH-26 bloque 2)."""
    id: str
    executed_at: str
    sale_folio: str
    method: str
    amount: str
    executed_by: str
    authorized_by: str


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
        if section_key == "payment_methods":
            return self._payment_methods(branch_id=branch_id,
                                         requester_user_id=requester_user_id)
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

    def refunds(self, *, branch_id: str, requester_user_id: str,
                limit: int = 200) -> tuple[CashRefundRow, ...]:
        """Reembolsos ejecutados en la sucursal: los registra la devolución del
        POS (SALES-23); aquí sólo se consultan, con folio y nombres."""
        self._authorization.require(user_id=requester_user_id,
                                    permission_code=CashPermissions.REFUND_VIEW,
                                    branch_id=branch_id)
        tables = {row[0] for row in self._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        folio = "s.sale_number" if "sales" in tables else "NULL"
        sales_join = "LEFT JOIN sales s ON s.id=r.sale_id" if "sales" in tables else ""
        if "usuarios" in tables:
            people = ("COALESCE(NULLIF(trim(ue.nombre),''),ue.usuario),"
                      "COALESCE(NULLIF(trim(ua.nombre),''),ua.usuario)")
            users_join = ("LEFT JOIN usuarios ue ON ue.id=r.executed_by "
                          "LEFT JOIN usuarios ua ON ua.id=r.authorized_by")
        else:
            people, users_join = "NULL,NULL", ""
        rows = self._connection.execute(
            f"""SELECT r.id,r.executed_at,{folio},r.method,r.amount,{people}
            FROM cash_refund_executions r {sales_join} {users_join}
            WHERE r.branch_id=? ORDER BY r.executed_at DESC,r.id DESC LIMIT ?""",
            (branch_id, max(1, min(int(limit or 200), 500)))).fetchall()
        return tuple(CashRefundRow(
            id=str(row[0]), executed_at=str(row[1] or ""), sale_folio=str(row[2] or ""),
            method=str(row[3] or ""), amount=str(row[4] or "0"),
            executed_by=str(row[5] or ""), authorized_by=str(row[6] or ""),
        ) for row in rows)

    def _payment_methods(self, *, branch_id: str,
                         requester_user_id: str) -> CashOperationalReadSection:
        """Medios de pago tal como Caja los LIQUIDA (CASH-26 bloque 2).

        La página leía `cash_payment_methods`, que nadie llena ni consulta: la
        regla real (qué entra al cajón y qué no) es `settlements.py`. Se muestra
        esa clasificación en vez de una tabla vacía."""
        self._authorization.require(user_id=requester_user_id,
                                    permission_code=CashPermissions.PAYMENT_METHOD_VIEW,
                                    branch_id=branch_id)
        rows = tuple(
            CashOperationalReadRow(
                id=definition.canonical_type,
                primary=_SETTLEMENT_NAMES.get(definition.canonical_type,
                                              definition.canonical_type),
                secondary=_SETTLEMENT_CLASSES[definition.classification.value],
                status=("FUTURE" if not definition.operational
                        else "AFFECTS_DRAWER" if definition.affects_drawer else "NO_DRAWER"),
                occurred_at="",
            )
            for definition in settlement_catalog()
        )
        return CashOperationalReadSection(key="payment_methods", title="Medios de pago",
                                          rows=rows)


_SETTLEMENT_NAMES = {
    "CASH": "Efectivo",
    "BANK_CARD": "Tarjeta bancaria",
    "BANK_TRANSFER": "Transferencia",
    "PAYMENT_LINK": "Liga de pago",
    "PAYMENT_PROCESSOR": "Procesador de pagos (Mercado Pago)",
    "CUSTOMER_CREDIT": "Credito a cliente",
    "LOYALTY_POINTS": "Puntos de lealtad",
    "COUPON": "Cupon",
    "VOUCHER": "Vale",
    "REFUND_VOUCHER": "Vale de devolucion",
    "PROMOTIONAL_VOUCHER": "Vale promocional",
    "STORE_CREDIT": "Saldo a favor",
    "PROMOTIONAL_BALANCE": "Saldo promocional",
    "GIFT_CARD": "Tarjeta de regalo",
}

_SETTLEMENT_CLASSES = {
    "PHYSICAL_CASH": "Dinero fisico: suma al esperado del corte",
    "ELECTRONIC": "Cobro electronico: se concilia con banco o procesador",
    "CREDIT": "Credito: genera cuenta por cobrar",
    "COMMERCIAL_INSTRUMENT": "Instrumento comercial: requiere validacion de Fidelidad",
    "FUTURE_INSTRUMENT": "Reservado: aun no se acepta en caja",
}
