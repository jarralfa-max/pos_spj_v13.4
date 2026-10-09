"""CRM-21 — Migración de consumidores: the legacy `clientes` <-> `customers`
identity bridge (migration 193), its resolver/backfill use cases, and the
real (now-subscribed) `core/events/wiring.py::_wire_customers_crm_sales_activity`
projection path this bridge unblocks.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.queries.customer_commercial_eligibility_query import (
    CustomerCommercialEligibilityQuery,
)
from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
    BackfillLegacyCustomersUseCase,
    EnsureLegacyCustomerBridgeUseCase,
    ResolveLegacyCustomerUseCase,
)
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.domain.customers.entities.customer_contact import CustomerContactPerson
from backend.domain.customers.exceptions import CustomerNotFoundError
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork
from backend.shared.ids import new_uuid


def _allow_cust():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _insert_legacy_cliente(conn, cliente_id: str, nombre: str = "Restaurante El Sol") -> None:
    conn.execute(
        "INSERT INTO clientes (id, nombre, telefono, activo) VALUES (?,?,?,1)",
        (cliente_id, nombre, "+525500000000"))
    conn.commit()


class TestResolveLegacyCustomerUseCase:
    def test_creates_bridge_row_on_first_reference(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-1", "Restaurante El Sol")
        new_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id="legacy-1")
        with CustomerUnitOfWork(conn) as uow:
            customer = uow.customers.get(new_id)
        assert customer is not None
        assert customer.legacy_customer_id == "legacy-1"
        assert customer.display_name == "Restaurante El Sol"

    def test_idempotent_on_repeat_calls(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-2")
        first = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id="legacy-2")
        second = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id="legacy-2")
        assert first == second
        with CustomerUnitOfWork(conn) as uow:
            assert uow.customers.get_by_legacy_customer_id("legacy-2").id == first

    def test_falls_back_to_placeholder_when_legacy_row_missing(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        new_id = ResolveLegacyCustomerUseCase().execute(
            conn, legacy_customer_id="ghost-legacy-id")
        with CustomerUnitOfWork(conn) as uow:
            customer = uow.customers.get(new_id)
        assert customer.display_name.startswith("Cliente ")
        assert customer.legacy_customer_id == "ghost-legacy-id"


class TestBackfillLegacyCustomersUseCase:
    def test_bridges_every_unbridged_cliente(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-a", "Cliente A")
        _insert_legacy_cliente(conn, "legacy-b", "Cliente B")
        result = BackfillLegacyCustomersUseCase().execute(conn, batch_size=500)
        assert result == {"created": 2, "remaining": 0}
        with CustomerUnitOfWork(conn) as uow:
            assert uow.customers.get_by_legacy_customer_id("legacy-a") is not None
            assert uow.customers.get_by_legacy_customer_id("legacy-b") is not None

    def test_skips_already_bridged_rows(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-c")
        ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id="legacy-c")
        result = BackfillLegacyCustomersUseCase().execute(conn, batch_size=500)
        assert result == {"created": 0, "remaining": 0}

    def test_resumable_with_small_batch_size(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        for i in range(5):
            _insert_legacy_cliente(conn, f"legacy-batch-{i}", f"Cliente {i}")
        use_case = BackfillLegacyCustomersUseCase()
        first = use_case.execute(conn, batch_size=2)
        assert first == {"created": 2, "remaining": 3}
        second = use_case.execute(conn, batch_size=2)
        assert second == {"created": 2, "remaining": 1}
        third = use_case.execute(conn, batch_size=2)
        assert third == {"created": 1, "remaining": 0}


class TestEnsureLegacyCustomerBridgeUseCase:
    """CRM-36 (Fase 2, §2) — the reverse bridge direction CRM-21 never
    built: a customer created NATIVELY in the Customer Master (never
    mirrored from a `clientes` row) gets one created on demand."""

    def _native_customer(self, conn, *, name="Cliente Nativo CRM") -> str:
        result = CreateCustomerUseCase(_allow_cust()).execute(
            conn, actor_user_id="u1", display_name=name, operation_id=new_uuid())
        assert result.success
        return result.entity_id

    def test_raises_for_unknown_customer(self, full_crm_conn_with_ops):
        with pytest.raises(CustomerNotFoundError):
            EnsureLegacyCustomerBridgeUseCase().execute(
                full_crm_conn_with_ops, customer_id="does-not-exist")

    def test_creates_legacy_row_for_native_customer(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = self._native_customer(conn, name="Restaurante El Sol")

        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)

        row = conn.execute(
            "SELECT nombre, activo FROM clientes WHERE id=?", (legacy_id,)).fetchone()
        assert row is not None
        assert row[0] == "Restaurante El Sol"
        assert row[1] == 1
        with CustomerUnitOfWork(conn) as uow:
            customer = uow.customers.get(customer_id)
        assert customer.legacy_customer_id == legacy_id

    def test_copies_primary_contact_phone_and_email(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = self._native_customer(conn)
        with CustomerUnitOfWork(conn) as uow:
            secondary = CustomerContactPerson.create(
                customer_id, "Secundario", phone_e164="+525511110000", is_primary=False)
            primary = CustomerContactPerson.create(
                customer_id, "Primario", phone_e164="+525599998888",
                email="primario@example.com", is_primary=True)
            uow.contacts.save(secondary)
            uow.contacts.save(primary)

        legacy_id = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)

        row = conn.execute(
            "SELECT telefono, email FROM clientes WHERE id=?", (legacy_id,)).fetchone()
        assert row[0] == "+525599998888"
        assert row[1] == "primario@example.com"

    def test_idempotent_never_creates_a_second_row(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = self._native_customer(conn)

        first = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)
        second = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)

        assert first == second
        count = conn.execute("SELECT COUNT(*) FROM clientes WHERE id=?", (first,)).fetchone()[0]
        assert count == 1

    def test_does_not_touch_already_bridged_customer(self, full_crm_conn_with_ops):
        """A customer bridged from the OTHER direction (legacy -> new,
        CRM-21) already has a real legacy row — must be returned as-is,
        never overwritten with a fresh mirror."""
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-existing", "Nombre Legacy Original")
        customer_id = ResolveLegacyCustomerUseCase().execute(
            conn, legacy_customer_id="legacy-existing")

        result = EnsureLegacyCustomerBridgeUseCase().execute(conn, customer_id=customer_id)

        assert result == "legacy-existing"
        count = conn.execute(
            "SELECT COUNT(*) FROM clientes WHERE nombre='Nombre Legacy Original'"
        ).fetchone()[0]
        assert count == 1


# CRM-43: `TestCustomersCrmSalesActivityWiring` probaba el cableado de
# `core/events/wiring.py`, borrado con la shell legacy. El cableado canónico
# de Ventas → Clientes vive en `backend/application/customers/integrations/
# sales_wiring.py` y tiene sus propias pruebas.


class TestCustomerCommercialEligibilityResolvesForLegacyOnlyCustomer:
    """Mirrors modulos/ventas.py's CRM-21 advisory checkout flow: resolve
    the legacy cliente_id first, THEN check eligibility — the query itself
    only understands the new customers.id."""

    def test_eligible_after_bridging(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-elig-1")
        new_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id="legacy-elig-1")
        result = CustomerCommercialEligibilityQuery(conn, _allow_cust()).check(
            new_id, actor_user_id="u1")
        assert result.eligible is True

    def test_ineligible_after_block_then_re_resolved(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        _insert_legacy_cliente(conn, "legacy-elig-2")
        new_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id="legacy-elig-2")
        with CustomerUnitOfWork(conn) as uow:
            customer = uow.customers.get(new_id)
            customer.block("mora")
            uow.customers.update(customer)
        # Same legacy id resolved again later (e.g. next sale) must hit the
        # same bridge row, not create a duplicate.
        re_resolved = ResolveLegacyCustomerUseCase().execute(
            conn, legacy_customer_id="legacy-elig-2")
        assert re_resolved == new_id
        result = CustomerCommercialEligibilityQuery(conn, _allow_cust()).check(
            re_resolved, actor_user_id="u1")
        assert result.eligible is False
