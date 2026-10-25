"""Cableado de Finanzas en el arranque (FIN-ERP, 2026-10-22).

- ``wire_finance`` suscribe los consumidores contables que no pertenecen a otro
  ``wire_*``: hoy, la merma valuada (``LOSS_FINANCE_RECOGNITION_REQUESTED``).
  Sólo suscribe; no toca la base.
- ``finance_periodic_tick`` siembra el catálogo (idempotente; antes sólo corría
  al abrir la vista de Finanzas, así que un Corte Z o una venta procesados antes
  no encontraban perfiles), entrega la merma pendiente, marca vencidos y
  despacha el ``finance_outbox``.
"""

from __future__ import annotations

from backend.application.event_handlers.finance.loss_recognition_handler import (
    LOSS_FINANCE_RECOGNITION_REQUESTED,
    LossRecognitionHandler,
)
from backend.application.services.finance.finance_bootstrap import bootstrap_finance


def wire_finance(bus, connection) -> dict:
    routes = ((LOSS_FINANCE_RECOGNITION_REQUESTED, LossRecognitionHandler(connection).handle),)
    for event_name, handler in routes:
        bus.subscribe(event_name, handler, priority=50,
                      label=f"finance_{event_name.lower()}")
    return {"subscribed": [f"{name}->finance" for name, _ in routes], "count": len(routes)}


def finance_periodic_tick(connection, bus, *, today=None) -> dict:
    """Ciclo de fondo de Finanzas: entrega la merma valuada pendiente, despacha
    el ``finance_outbox`` y marca CxC/CxP vencidas (idempotente por día)."""
    from datetime import date

    from backend.application.losses.outbox_dispatcher import dispatch_loss_outbox
    from backend.application.services.finance.outbox_dispatcher import dispatch_finance_outbox
    from backend.application.use_cases.finance.mark_overdue_documents_use_case import (
        MarkOverdueDocumentsUseCase,
    )
    from backend.infrastructure.persistence.loss_outbox_repository import LossOutboxRepository

    bootstrap_finance(connection)
    losses = dispatch_loss_outbox(LossOutboxRepository(connection), bus)
    overdue = MarkOverdueDocumentsUseCase().execute(connection, as_of=today or date.today())
    finance = dispatch_finance_outbox(connection, bus)
    return {"losses": losses, "finance": finance,
            "overdue": {"receivables": overdue.receivables, "payables": overdue.payables}}
