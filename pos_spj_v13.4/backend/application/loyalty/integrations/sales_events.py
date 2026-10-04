"""Consumidores de Fidelidad para los eventos de Ventas (2026-10-02).

`SALE_COMPLETED` acredita los puntos de la compra; `SALE_RETURNED` y
`SALE_REVERSED` los retiran en proporción. `SALE_CANCELLED` y `SALE_REVERSED`
devuelven además lo que el cliente canjeó en esa venta. Viven del lado de Fidelidad (dueña
de los puntos); Ventas sólo publica. La autorización es la DELEGADA de
`sale_points_use_cases.SALES_GRANT`, en nombre del cajero que originó el
evento.
"""

from __future__ import annotations

from decimal import Decimal

from backend.application.loyalty.use_cases.sale_points_use_cases import (
    AccrueSalePointsUseCase,
    RemoveSalePointsUseCase,
    RestoreSaleRedemptionUseCase,
    delegated_policy,
)


def _dec(value) -> Decimal:
    return Decimal(str(value or "0"))


def _fail_loud(result, evento: str) -> None:
    """Un fallo de Fidelidad deja el evento PENDIENTE en el outbox de Ventas
    (se reintenta en el siguiente despacho) en vez de perder los puntos."""
    if not result.success:
        raise RuntimeError(f"Fidelidad no procesó {evento}: {result.message}")


class SaleLoyaltyEventHandlers:
    def __init__(self, connection) -> None:
        self._conn = connection

    def on_sale_completed(self, envelope: dict) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        credito = sum((_dec(p.get("amount")) for p in datos.get("payments") or []
                       if str(p.get("method")) == "CREDIT"), Decimal("0"))
        _fail_loud(AccrueSalePointsUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"), total=_dec(datos.get("total")),
            credit_amount=credito, branch_id=str(envelope.get("branch_id")),
            actor_user_id=actor, operation_id=str(envelope.get("event_id")),
            occurred_at=envelope.get("timestamp"), lines=datos.get("lines") or (),
            payments=datos.get("payments") or (),
            channel=str(datos.get("channel") or "POS")), "SALE_COMPLETED")

    def on_sale_returned(self, envelope: dict) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        _fail_loud(RemoveSalePointsUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"),
            document_id=str(datos.get("return_id") or envelope.get("event_id")),
            sale_total=_dec(datos.get("sale_total")),
            refunded_total=_dec(datos.get("refunded_total") or datos.get("amount")),
            branch_id=str(envelope.get("branch_id")), actor_user_id=actor,
            operation_id=str(envelope.get("event_id"))), "SALE_RETURNED")

    def on_sale_reversed(self, envelope: dict) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        total = _dec(datos.get("sale_total"))
        _fail_loud(RemoveSalePointsUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"), document_id=str(envelope.get("entity_id")),
            sale_total=total, refunded_total=total, branch_id=str(envelope.get("branch_id")),
            actor_user_id=actor, operation_id=str(envelope.get("event_id"))), "SALE_REVERSED")
        self._restore_redemption(envelope, "SALE_REVERSED")

    def on_sale_cancelled(self, envelope: dict) -> None:
        self._restore_redemption(envelope, "SALE_CANCELLED")

    def _restore_redemption(self, envelope: dict, evento: str) -> None:
        datos = dict(envelope.get("payload") or {})
        actor = str(envelope.get("user_id") or "")
        _fail_loud(RestoreSaleRedemptionUseCase(delegated_policy(actor)).execute(
            self._conn, sale_id=str(envelope.get("entity_id")),
            customer_id=datos.get("customer_id"), branch_id=str(envelope.get("branch_id")),
            actor_user_id=actor, operation_id=str(envelope.get("event_id"))), evento)
