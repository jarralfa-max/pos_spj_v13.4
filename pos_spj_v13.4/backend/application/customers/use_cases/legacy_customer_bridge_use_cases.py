"""Legacy identity bridge (CRM-21, "Migración de consumidores").

The Customer Master (`customers`, CRM-3) and the legacy `clientes` table
(all real production data — POS/Ventas/WhatsApp/Delivery/Fidelidad/Finanzas
all still read/write `clientes` directly) are two separate tables with
independently-minted UUIDv7 ids and no relationship between them. This
module builds the missing bridge: given a legacy `clientes.id`, resolve (or
lazily create) the corresponding `customers` row via
`customers.legacy_customer_id` (migration 193).

Same reasoning as `sales_integration_use_cases.py` for why these use cases
take no `actor_user_id`/permission check: bridging is a system-triggered
side effect of reading/reacting to another bounded context's data, not a
direct user action against the Customer Master. Unlike
`CreateCustomerUseCase`, this intentionally skips `CustomerDuplicatePolicy`
matching — a bridge row's whole purpose is to mirror one specific legacy
record 1:1, not to find/merge with an unrelated similar-looking one.

**Read-only reference to `clientes`** (a different bounded context's table)
is the same sanctioned exception CRM-13's own summary queries already rely
on (`customer_orders_summary_query.py` et al.) — this module never writes to
`clientes`.
"""

from __future__ import annotations

import json

from backend.domain.customers.entities.customer import Customer
from backend.domain.customers.enums import CustomerType
from backend.domain.customers.events import CustomerEvents, build_event_payload
from backend.domain.customers.exceptions import CustomerNotFoundError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork
from backend.shared.ids import new_uuid


def _legacy_display_name(connection, legacy_customer_id: str) -> str:
    row = connection.execute(
        "SELECT nombre FROM clientes WHERE id=?", (legacy_customer_id,)).fetchone()
    name = (row[0] if row else "") or ""
    return name.strip() or f"Cliente {legacy_customer_id[:8]}"


class ResolveLegacyCustomerUseCase:
    """Returns the `customers.id` bridged to `legacy_customer_id`, creating
    the bridge row on first reference. Never raises: an unresolvable legacy
    id still yields a valid new customer with a placeholder display name
    (see `_legacy_display_name`), because callers (event handlers, read-path
    wiring) must never fail a sale or a chat reply over a bridging gap."""

    def execute(self, connection, *, legacy_customer_id: str,
                source: str = "legacy_bridge") -> str:
        with CustomerUnitOfWork(connection) as uow:
            existing = uow.customers.get_by_legacy_customer_id(legacy_customer_id)
            if existing is not None:
                return existing.id
            display_name = _legacy_display_name(connection, legacy_customer_id)
            customer = Customer.create(
                uow.customers.next_code(), display_name, CustomerType.INDIVIDUAL,
                source=source, legacy_customer_id=legacy_customer_id)
            uow.customers.save(customer)
            uow.audit.record(
                action=CustomerEvents.CREATED, actor_user_id=None, customer_id=customer.id,
                after_json=json.dumps({"display_name": display_name,
                                      "legacy_customer_id": legacy_customer_id}),
                reason="bridge_legacy")
            payload = build_event_payload(
                CustomerEvents.CREATED, operation_id=customer.operation_id or customer.id,
                customer_id=customer.id, source_module="customers_legacy_bridge")
            uow.outbox.enqueue(payload["event_id"], CustomerEvents.CREATED,
                               json.dumps(payload), payload["operation_id"])
            return customer.id


class EnsureLegacyCustomerBridgeUseCase:
    """Fase 2 (§2, "IDENTIDAD ÚNICA DE CLIENTE") — the bridge direction
    CRM-21 never built. `ResolveLegacyCustomerUseCase` only goes
    legacy → new; a customer created NATIVELY in the Customer Master
    (e.g. via the CRM "Nuevo cliente" page, never mirrored from a
    `clientes` row) has no legacy record — every legacy-only consumer
    (Ventas checkout, WhatsApp's phone lookup, Delivery, Fidelidad) is
    unable to select or transact with them. Documented as an explicit,
    honest limitation by CRM-32's `ModuloVentas.aplicar_contexto`
    ("Cliente sin registro en Ventas") rather than silently failing —
    this use case closes that gap by creating the missing `clientes` row
    on demand and pointing `customers.legacy_customer_id` at it.

    Idempotent: if `legacy_customer_id` is already set (bridged from
    either direction), returns it unchanged — never creates a second
    `clientes` row for the same customer. `customers.legacy_customer_id`
    is otherwise write-once-at-creation in `CustomerRepository.update()`
    (by design — it's provenance, not an editable field); this is the one
    sanctioned exception, a direct targeted `UPDATE` for exactly that
    column, mirroring `ResolveLegacyCustomerUseCase`'s already-sanctioned
    direct-SQL read into `clientes` (a different bounded context's table,
    read/written only for bridging, never for business logic)."""

    def execute(self, connection, *, customer_id: str) -> str:
        with CustomerUnitOfWork(connection) as uow:
            customer = uow.customers.get(customer_id)
            if customer is None:
                raise CustomerNotFoundError(f"Customer {customer_id} no existe")
            if customer.legacy_customer_id:
                return customer.legacy_customer_id

            contacts = uow.contacts.list_for_customer(customer_id)
            primary = next((c for c in contacts if c.is_primary), None) or (
                contacts[0] if contacts else None)
            telefono = (primary.phone_e164 if primary else "") or ""
            email = (primary.email if primary else "") or ""

            legacy_customer_id = new_uuid()
            connection.execute(
                "INSERT INTO clientes (id, nombre, telefono, email, activo)"
                " VALUES (?, ?, ?, ?, 1)",
                (legacy_customer_id, customer.display_name, telefono, email))
            connection.execute(
                "UPDATE customers SET legacy_customer_id=? WHERE id=?",
                (legacy_customer_id, customer_id))
            uow.audit.record(
                action=CustomerEvents.UPDATED, actor_user_id=None, customer_id=customer_id,
                after_json=json.dumps({"legacy_customer_id": legacy_customer_id}),
                reason="reverse_bridge_ensured")
            return legacy_customer_id


class BackfillLegacyCustomersUseCase:
    """One-time/resumable batch backfill: creates a bridge `customers` row
    for every `clientes` row that doesn't have one yet. Shares
    `ResolveLegacyCustomerUseCase`'s creation logic (called per row) so the
    lazy and bulk paths can never diverge."""

    def execute(self, connection, *, batch_size: int = 500) -> dict:
        rows = connection.execute(
            "SELECT id FROM clientes WHERE id NOT IN"
            " (SELECT legacy_customer_id FROM customers WHERE legacy_customer_id IS NOT NULL)"
            " LIMIT ?", (batch_size,)).fetchall()
        unbridged_ids = [row[0] for row in rows]
        resolver = ResolveLegacyCustomerUseCase()
        for clientes_row_id in unbridged_ids:
            resolver.execute(connection, legacy_customer_id=clientes_row_id, source="backfill")
        remaining = connection.execute(
            "SELECT COUNT(*) FROM clientes WHERE id NOT IN"
            " (SELECT legacy_customer_id FROM customers WHERE legacy_customer_id IS NOT NULL)"
        ).fetchone()[0]
        return {"created": len(unbridged_ids), "remaining": remaining}
