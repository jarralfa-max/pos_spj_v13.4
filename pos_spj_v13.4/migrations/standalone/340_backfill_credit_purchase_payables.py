"""340 — CxP de las compras rápidas a CRÉDITO ya recibidas (2026-10-15).

Hasta hoy la cuenta por pagar de una compra a crédito sólo nacía al conciliar la
factura del proveedor; en la base real había 4 compras a crédito recibidas
($9,066) y CERO cuentas por pagar. Decisión del usuario: la CxP nace al recibir,
y las compras ya recibidas se regularizan.

Por cada recepción COMPLETADA de una compra a crédito que no tenga factura
conciliada, se encola la misma solicitud que hoy emite la recepción
(``ACCOUNT_PAYABLE_CREATE_REQUESTED``), fechada en la recepción y con vencimiento
según los días de crédito del proveedor. La identidad es la de la recepción
(clave de deduplicación + operación derivada): volver a correr no duplica y
Finanzas tampoco aplica dos veces. Se entrega al arrancar (despacho del outbox de
Compras) o en la siguiente operación de Compras.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone

from backend.shared.business_dates import local_business_date

logger = logging.getLogger("spj.migrations.340")


def _tabla(conn, nombre: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                        (nombre,)).fetchone() is not None


def _period_closed(conn, day) -> bool:
    if not _tabla(conn, "fiscal_periods"):
        return False
    columns = {r[1] for r in conn.execute("PRAGMA table_info(fiscal_periods)")}
    if "code" in columns:
        row = conn.execute("SELECT status FROM fiscal_periods WHERE code=?",
                           (day.strftime("%Y-%m"),)).fetchone()
    elif {"year", "month"} <= columns:
        row = conn.execute("SELECT status FROM fiscal_periods WHERE year=? AND month=?",
                           (day.year, day.month)).fetchone()
    else:
        return False
    # Sólo un periodo ABIERTO admite asientos (cerrado o en precierre, no).
    return bool(row) and str(row[0]).upper() != "OPEN"


def run(conn) -> None:
    if not (_tabla(conn, "direct_purchases") and _tabla(conn, "procurement_outbox")):
        logger.info("340: sin esquema de Compras; nada que regularizar.")
        return
    from backend.application.procurement.supplier_credit import SupplierCreditService
    from backend.application.procurement.use_cases.direct_purchase_use_cases import (
        receipt_value,
    )
    from backend.domain.procurement.events import ProcurementEvents, build_event_payload
    from backend.infrastructure.db.repositories.procurement.unit_of_work import (
        ProcurementUnitOfWork,
    )
    from backend.shared.ids import derived_uuidv7

    credit = SupplierCreditService(conn)
    queued = skipped = 0
    candidates = [r[0] for r in conn.execute(
        "SELECT id FROM direct_purchases WHERE payment_condition='SUPPLIER_CREDIT'"
        " AND status IN ('RECEIVED','PARTIALLY_RECEIVED')")]
    with ProcurementUnitOfWork(conn) as uow:
        for dp_id in candidates:
            invoiced = conn.execute(
                "SELECT 1 FROM supplier_invoices WHERE direct_purchase_id=? AND status IN"
                " ('MATCHED','APPROVED','POSTED') LIMIT 1", (dp_id,)).fetchone()
            if invoiced:   # su CxP ya nació por la factura (regla anterior)
                skipped += 1
                continue
            dp = uow.direct_purchases.get(dp_id)
            if dp is None:
                continue
            terms = credit.terms(dp.supplier_id)
            days = terms.credit_days if terms is not None and terms.is_credit else 0
            for gr in uow.receipts.completed_for_document(direct_purchase_id=dp.id):
                key = f"DIRECT_PURCHASE_RECEIPT:{gr.id}"
                if conn.execute("SELECT 1 FROM procurement_outbox WHERE deduplication_key=?",
                                (key,)).fetchone():
                    continue
                value = receipt_value(dp, gr)
                if value is None:
                    continue
                natures, tax, amount = value
                payload = build_event_payload(
                    ProcurementEvents.ACCOUNT_PAYABLE_CREATE_REQUESTED,
                    operation_id=derived_uuidv7(gr.id, "credit-receipt-payable"),
                    document_id=gr.id,
                    document_number=f"{dp.document_number} / {gr.document_number}",
                    supplier_id=dp.supplier_id, branch_id=dp.branch_id,
                    amount=format(amount, "f"), currency_code=dp.currency_code,
                    nature_subtotals=natures, tax_total=format(tax, "f"),
                    payment_term_days=days, payment_condition=dp.payment_condition.value,
                    source_type="DIRECT_PURCHASE_RECEIPT", source_id=gr.id,
                    deduplication_key=key, backfill="340")
                payload["timestamp"] = gr.created_at   # fecha de la recepción
                received_on = local_business_date(gr.created_at)
                if _period_closed(conn, received_on):
                    # No se toca un periodo cerrado: se reconoce HOY, pero vence
                    # cuando vencía según la recepción original.
                    payload["timestamp"] = datetime.now(timezone.utc).isoformat(
                        timespec="seconds")
                    payload["due_date"] = (received_on + timedelta(days=days)).isoformat()
                    payload["document_number"] += f" (recibida {received_on.isoformat()})"
                try:
                    uow.outbox.enqueue(event_id=payload["event_id"],
                                       event_name=ProcurementEvents.ACCOUNT_PAYABLE_CREATE_REQUESTED,
                                       payload_json=json.dumps(payload),
                                       operation_id=payload["operation_id"],
                                       deduplication_key=key)
                except sqlite3.IntegrityError:
                    continue
                queued += 1
    conn.commit()
    logger.info("340: %s CxP de recepciones a crédito encoladas; %s compras ya facturadas",
                queued, skipped)


up = run
