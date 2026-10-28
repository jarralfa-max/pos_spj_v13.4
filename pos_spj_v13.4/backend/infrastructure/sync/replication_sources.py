"""De dónde toma el motor de replicación los hechos: los outbox de contexto
(arquitectura híbrida, Slice 2; ADR-004 «los outbox de contexto son la fuente»).

Cada contexto ya escribe su evento canónico en su outbox, EN LA MISMA
transacción que el hecho (Slice 0 lo garantiza en cualquier conexión). Aquí sólo
se LEE: el motor nunca cambia el `status` de esas filas, que pertenece a su
despachador en proceso (Caja → Finanzas, Compras → CxP…).

Las tablas no son idénticas (`event_name`/`event_type`, `payload_json`/
`payload`, con o sin `event_id`, `entity_id` o `aggregate_id`). `normalize()`
las lleva a la forma canónica que entiende `envelope_from_outbox_event`:
`event_id`, `event_name`, `operation_id`, `entity_id`, `branch_id`, `user_id`,
`timestamp`, `payload`. Lo que falte se deriva de forma DETERMINISTA del id de
la fila (`derived_uuidv7`), para que un reintento produzca el mismo sobre.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend.shared.ids import derived_uuidv7, is_uuidv7


#: Campos que son identidad del sobre, no datos del hecho.
_ENVELOPE_KEYS = frozenset({"event_id", "event_name", "operation_id", "entity_id", "branch_id",
                            "user_id", "timestamp", "correlation_id", "causation_id"})


@dataclass(frozen=True)
class ReplicationSource:
    #: Nombre estable del contexto (forma parte de `aggregate_type`).
    name: str
    table: str
    #: Agregado por omisión cuando la fila no trae `aggregate_type`.
    default_aggregate: str = "record"

    def exists(self, conn) -> bool:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                            (self.table,)).fetchone() is not None

    def columns(self, conn) -> set[str]:
        return {r[1] for r in conn.execute(f'PRAGMA table_info("{self.table}")')}

    def pending_rows(self, conn, *, limit: int) -> list[dict]:
        """Filas del outbox que todavía no tienen sobre, en orden de creación."""
        orden = "created_at" if "created_at" in self.columns(conn) else "rowid"
        cursor = conn.execute(
            f'SELECT o.* FROM "{self.table}" o'
            " WHERE NOT EXISTS (SELECT 1 FROM replication_envelopes r"
            "                   WHERE r.source = ? AND r.source_row_id = o.id)"
            f" ORDER BY o.{orden}, o.id LIMIT ?", (self.name, limit))
        nombres = [c[0] for c in cursor.description]
        return [dict(zip(nombres, fila)) for fila in cursor.fetchall()]

    def normalize(self, row: dict, *, station_branch_id: str) -> tuple[dict, str]:
        """(evento canónico, aggregate_type) de una fila del outbox."""
        crudo = row.get("payload_json", row.get("payload"))
        try:
            cuerpo = json.loads(crudo) if isinstance(crudo, str) and crudo else (crudo or {})
        except ValueError:
            cuerpo = {"raw": crudo}
        if not isinstance(cuerpo, dict):
            cuerpo = {"value": cuerpo}
        canonico = all(k in cuerpo for k in ("event_id", "payload")) and "timestamp" in cuerpo
        # Evento «plano» (Inventario: sus datos al mismo nivel que el sobre): el
        # payload que viaja es lo que NO es identidad del sobre.
        datos = cuerpo.get("payload", {}) if canonico else {
            k: v for k, v in cuerpo.items() if k not in _ENVELOPE_KEYS}
        fila_id = str(row["id"])

        def primero(*valores):
            return next((v for v in valores if v not in (None, "")), None)

        def uuid_o_derivado(valor, etiqueta):
            return valor if is_uuidv7(valor) else derived_uuidv7(
                f"{self.name}:{fila_id}", etiqueta)

        evento = {
            "event_id": uuid_o_derivado(primero(cuerpo.get("event_id"), row.get("event_id")),
                                        "replication-event"),
            "event_name": primero(cuerpo.get("event_name"), row.get("event_name"),
                                  row.get("event_type")),
            "operation_id": uuid_o_derivado(
                primero(cuerpo.get("operation_id"), row.get("operation_id")),
                "replication-operation"),
            "entity_id": uuid_o_derivado(
                primero(cuerpo.get("entity_id"), row.get("entity_id"), row.get("aggregate_id")),
                "replication-aggregate"),
            "branch_id": primero(cuerpo.get("branch_id"), datos.get("branch_id")
                                 if isinstance(datos, dict) else None, station_branch_id),
            "user_id": primero(cuerpo.get("user_id"), cuerpo.get("actor_user_id")),
            "timestamp": _instante(primero(cuerpo.get("timestamp"), cuerpo.get("occurred_at"),
                                           row.get("occurred_at"), row.get("created_at"))),
            "payload": datos,
            "correlation_id": primero(cuerpo.get("correlation_id"), row.get("correlation_id")),
            "causation_id": primero(cuerpo.get("causation_id"), row.get("causation_id")),
        }
        if evento["user_id"] is not None and not is_uuidv7(evento["user_id"]):
            evento["user_id"] = None   # actores legacy no UUIDv7: viajan sin actor
        for clave in ("correlation_id", "causation_id"):
            if evento[clave] is not None and not is_uuidv7(evento[clave]):
                evento[clave] = None
        agregado = primero(row.get("aggregate_type"), self.default_aggregate)
        return evento, f"{self.name}.{_slug(agregado)}"


def _instante(valor) -> str:
    """ISO con zona. Las filas sin zona se escribieron en UTC (todo el repo usa
    `datetime.now(timezone.utc)`); se les pone explícitamente."""
    if not valor:
        return datetime.now(timezone.utc).isoformat()
    try:
        instante = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc).isoformat()
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=timezone.utc)
    return instante.isoformat()


def _slug(texto: str) -> str:
    limpio = "".join(c if c.isalnum() else "_" for c in str(texto).lower()).strip("_")
    return limpio if limpio and limpio[0].isalpha() else f"a_{limpio or 'record'}"


#: Outbox que se replican. Las tablas que no existan en una instalación se
#: omiten. Un contexto nuevo se agrega aquí, no con un motor propio.
DEFAULT_SOURCES: tuple[ReplicationSource, ...] = (
    ReplicationSource("cash_register", "cash_outbox", "cash"),
    ReplicationSource("sales", "sales_outbox", "sale"),
    ReplicationSource("inventory", "inventory_outbox", "stock"),
    ReplicationSource("finance", "finance_outbox", "ledger"),
    ReplicationSource("procurement", "procurement_outbox", "purchase"),
    ReplicationSource("loyalty", "loyalty_outbox", "membership"),
    ReplicationSource("commercial_instruments", "commercial_instruments_outbox", "instrument"),
    ReplicationSource("customers", "customer_outbox", "customer"),
    ReplicationSource("customer_credit", "customer_credit_outbox", "credit_account"),
    ReplicationSource("losses", "loss_outbox", "loss_case"),
    ReplicationSource("transfers", "transfer_outbox", "transfer"),
    ReplicationSource("meat_processing", "meat_processing_outbox", "processing_order"),
    ReplicationSource("costing", "costing_outbox", "cost"),
    ReplicationSource("quality", "quality_outbox", "inspection"),
    ReplicationSource("hr", "hr_outbox", "employee"),
    ReplicationSource("logistics", "logistics_outbox", "shipment"),
    ReplicationSource("orders_delivery", "orders_delivery_outbox", "order"),
    ReplicationSource("pricing", "pricing_outbox", "price_list"),
    ReplicationSource("products", "product_outbox", "product"),
    ReplicationSource("suppliers", "supplier_outbox", "supplier"),
    ReplicationSource("crm", "crm_outbox", "lead"),
    ReplicationSource("customer_service", "customer_service_outbox", "case"),
    ReplicationSource("customer_privacy", "customer_privacy_outbox", "consent"),
    ReplicationSource("loyalty_cards", "loyalty_cards_outbox", "card"),
    ReplicationSource("sweepstakes", "sweepstakes_outbox", "campaign"),
    ReplicationSource("quotes", "quote_outbox", "quote"),
    ReplicationSource("organization", "org_outbox", "org_unit"),
)
# Fuera a propósito: `whatsapp_outbox` y `product_whatsapp_outbox` son colas de
# MENSAJES por enviar (su propio despachador los entrega), no hechos de negocio;
# `sync_outbox`, `event_outbox` y `delivery_outbox_events` son legados sin
# escritor canónico.


__all__ = ["DEFAULT_SOURCES", "ReplicationSource"]
