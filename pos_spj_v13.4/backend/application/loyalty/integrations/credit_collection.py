"""Puntos de lo vendido a crédito, al cobrarse (auditoría 968e0bc FID-04).

Finanzas publica `COLLECTION_APPLIED` por cada parte de un cobro aplicada a una
CxC; antes nadie lo escuchaba. Si la CxC es de una venta con puntos pendientes,
se acredita la parte proporcional a lo cobrado, UNA vez por aplicación.
"""

from __future__ import annotations

import logging
from decimal import ROUND_DOWN, Decimal

logger = logging.getLogger("spj.loyalty.credit_collection")

REASON = "CREDIT_COLLECTED"
SOURCE_MODULE = "credit_collection"


class CreditCollectionLoyaltyHandler:
    def __init__(self, connection) -> None:
        self._conn = connection

    def handle(self, envelope: dict) -> None:
        from backend.application.loyalty.queries.program_settings_query import (
            LoyaltyProgramSettingsQuery,
        )
        from backend.application.loyalty.use_cases.ledger_use_cases import (
            AccrueLoyaltyPointsUseCase,
        )
        from backend.application.loyalty.use_cases.sale_points_use_cases import (
            delegated_policy,
        )
        from backend.domain.loyalty.policies.accrual_policy import LoyaltyAccrualPolicy
        from backend.infrastructure.db.repositories.loyalty.deferred_accrual_repository import (
            LoyaltyDeferredAccrualRepository,
        )
        from backend.infrastructure.db.repositories.loyalty.unit_of_work import (
            LoyaltyUnitOfWork,
        )
        from backend.shared.ids import new_uuid

        datos = dict(envelope.get("payload") or envelope)
        repo = LoyaltyDeferredAccrualRepository(self._conn)
        if not repo.schema_ready():
            return
        aplicacion = str(datos.get("entity_id") or envelope.get("entity_id") or "")
        receivable = str(datos.get("receivable_id") or "")
        if not aplicacion or not receivable or repo.has_collection(aplicacion):
            return
        sale_id = repo.sale_of_receivable(receivable)
        pendiente = repo.get(sale_id) if sale_id else None
        if pendiente is None or pendiente["status"] != "OPEN":
            return
        importe = Decimal(str(datos.get("applied_amount") or "0"))
        cobrado = pendiente["collected_amount"] + importe
        proporcion = (min(cobrado / pendiente["credit_amount"], Decimal("1"))
                      if pendiente["credit_amount"] > 0 else Decimal("1"))
        objetivo = int((pendiente["deferred_points"] * proporcion)
                       .to_integral_value(rounding=ROUND_DOWN))
        nuevos = max(objetivo - int(pendiente["accrued_points"]), 0)
        cuenta = pendiente["loyalty_account_id"]
        if nuevos > 0 and not cuenta:
            # Una venta TODA a crédito no acumuló nada al vender y por eso no
            # abrió la cuenta: se abre aquí, igual que en la primera compra.
            from backend.domain.loyalty.entities.loyalty_account import LoyaltyAccount
            with LoyaltyUnitOfWork(self._conn) as uow:
                encontrada = uow.accounts.get_by_customer_id(pendiente["customer_id"])
                if encontrada is None:
                    encontrada = LoyaltyAccount.create(pendiente["customer_id"])
                    uow.accounts.save(encontrada)
                cuenta = encontrada.id
        if nuevos > 0:
            ajustes = LoyaltyProgramSettingsQuery(self._conn).accrual()
            from datetime import datetime, timezone
            from backend.domain.loyalty.events import SYSTEM_ACTOR_ID
            # El evento de Finanzas no trae al usuario: lo acredita el sistema.
            actor = str(envelope.get("user_id") or SYSTEM_ACTOR_ID)
            resultado = AccrueLoyaltyPointsUseCase(delegated_policy(actor)).execute(
                self._conn, loyalty_account_id=cuenta, points_amount=Decimal(nuevos),
                operation_id=new_uuid(), actor_user_id=actor,
                actor_branch_id=pendiente["branch_id"] or "", source_module=SOURCE_MODULE,
                reason_code=REASON, source_document_id=aplicacion, sale_id=sale_id,
                expires_at=LoyaltyAccrualPolicy.expires_at(datetime.now(timezone.utc),
                                                           ajustes))
            if not resultado.success and "Ya existe una acreditación" not in (
                    resultado.message or ""):
                raise RuntimeError(f"Fidelidad no acreditó el cobro a crédito: "
                                   f"{resultado.message}")
        repo.record_collection(
            application_id=aplicacion, sale_id=sale_id, amount=importe, points=nuevos,
            collected_total=cobrado, accrued_total=int(pendiente["accrued_points"]) + nuevos,
            closed=proporcion >= 1)
        self._conn.commit()


def wire_loyalty_finance(bus, connection) -> dict:
    """Fidelidad escucha a Finanzas: el cobro de lo vendido a crédito."""
    from backend.shared.events.event_names import EventName

    manejador = CreditCollectionLoyaltyHandler(connection)
    subscribe = getattr(bus, "subscribe", None)
    if subscribe is None:
        raise RuntimeError("El bus no expone subscribe()")
    try:
        subscribe(EventName.COLLECTION_APPLIED.value, manejador.handle, priority=10,
                  label="loyalty_credit_collected")
    except TypeError:
        subscribe(EventName.COLLECTION_APPLIED.value, manejador.handle)
    return {"subscribed": ["in:COLLECTION_APPLIED->loyalty"], "count": 1}
