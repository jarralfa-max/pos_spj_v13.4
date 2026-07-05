from __future__ import annotations

import json
from typing import Any, Dict, Iterable

from backend.shared.ids import new_uuid


class ScheduledDemandService:
    """Persist scheduled WhatsApp demand and emit FORECAST_DEMAND_UPDATED traces."""

    def __init__(self, db):
        self.db = db

    def register_scheduled_sale(
        self,
        *,
        sale_id: str,
        branch_id: str,
        customer_id: str | None,
        folio: str,
        scheduled_at: str,
        items: Iterable[Dict[str, Any]],
        source_channel: str = "whatsapp",
    ) -> int:
        if not scheduled_at:
            return 0

        # Schema lo crean las migraciones 091/050 (REGLA 11): el servicio no crea schema.
        affected = 0
        for item in items:
            product_id = str(item.get("product_id") or item.get("producto_id") or "")
            if not product_id:
                continue
            quantity = float(item.get("cantidad") or item.get("quantity") or 0)
            unit = item.get("unidad") or item.get("unit") or "kg"
            self.db.execute(
                """
                INSERT INTO scheduled_demand_events (
                    sale_id, branch_id, product_id, quantity, unit,
                    scheduled_at, source_channel, customer_id, folio, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(sale_id, product_id, scheduled_at)
                DO UPDATE SET
                    quantity=excluded.quantity,
                    unit=excluded.unit,
                    source_channel=excluded.source_channel,
                    customer_id=excluded.customer_id,
                    folio=excluded.folio
                """,
                (sale_id, branch_id, product_id, quantity, unit, scheduled_at, source_channel, customer_id, folio),
            )
            self.db.execute(
                """
                INSERT INTO wa_event_log(id, event_type, data_json, sucursal_id, prioridad, timestamp)
                VALUES (?, ?, ?, ?, 50, datetime('now'))
                """,
                (
                    new_uuid(),
                    "FORECAST_DEMAND_UPDATED",
                    json.dumps({
                        "branch_id": branch_id,
                        "product_id": product_id,
                        "quantity": quantity,
                        "unit": unit,
                        "scheduled_at": scheduled_at,
                        "source_channel": source_channel,
                        "sale_id": sale_id,
                        "folio": folio,
                        "customer_id": customer_id,
                    }, ensure_ascii=False),
                    branch_id,
                ),
            )
            affected += 1
        self.db.commit()
        return affected
