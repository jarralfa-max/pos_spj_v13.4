"""CRM-3 — Customer Master application tests (use cases + query service).

Covers happy path, permission-denied (fail closed, no checker), invalid
state, duplicate detection, idempotency, rollback, events, audit, and scope
enforcement in the query service.
"""

from __future__ import annotations

import json

import pytest

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.data_scope import (
    CustomerDataScopeResolver,
    CustomerScopeContext,
)
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.queries.customer_profile_query_service import (
    CustomerProfileQueryService,
)
from backend.application.customers.use_cases.address_use_cases import (
    AddCustomerAddressUseCase,
    RemoveCustomerAddressUseCase,
    SetDefaultCustomerAddressUseCase,
    UpdateCustomerAddressUseCase,
)
from backend.application.customers.use_cases.contact_use_cases import (
    AddCustomerContactUseCase,
    RemoveCustomerContactUseCase,
    SetPrimaryCustomerContactUseCase,
    UpdateCustomerContactUseCase,
)
from backend.application.customers.use_cases.lifecycle_use_cases import (
    ActivateCustomerUseCase,
    BlockCustomerUseCase,
    CloseCustomerUseCase,
    CreateCustomerUseCase,
    DeactivateCustomerUseCase,
    SuspendCustomerUseCase,
    UpdateCustomerUseCase,
)
from backend.application.customers.use_cases.tax_profile_use_cases import (
    UpdateCustomerTaxProfileUseCase,
)
from backend.domain.customers.exceptions import CustomerNotFoundError, CustomerScopeError
from backend.shared.ids import new_uuid


def _allow_all():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _create(conn, *, actor="u-capturista", name="Juan Perez", operation_id=None, **kwargs):
    return CreateCustomerUseCase(_allow_all()).execute(
        conn, actor_user_id=actor, display_name=name,
        operation_id=operation_id or new_uuid(), **kwargs)


class TestCreate:
    def test_happy_path_emits_event_and_audit(self, cust_conn):
        result = _create(cust_conn)
        assert result.success and result.entity_id
        assert result.data["code"] == "CLI-000001"
        outbox = cust_conn.execute(
            "SELECT COUNT(*) FROM customer_outbox WHERE event_name='CUSTOMER_CREATED'"
        ).fetchone()[0]
        audit = cust_conn.execute(
            "SELECT COUNT(*) FROM customer_audit_log WHERE action='CUSTOMER_CREATED'"
        ).fetchone()[0]
        assert outbox == 1 and audit == 1

    def test_permission_denied_without_checker_wired(self, cust_conn):
        # Default CustomerAuthorizationPolicy() has no checker → fail closed.
        result = CreateCustomerUseCase().execute(
            cust_conn, actor_user_id="u1", display_name="X", operation_id=new_uuid())
        assert not result.success and result.error_code == "PERMISSION_DENIED"

    def test_duplicate_detected_not_merged(self, cust_conn):
        _create(cust_conn, phone_e164="+525512345678")
        dup = _create(cust_conn, name="Juan Perez", phone_e164="+525512345678")
        assert not dup.success and dup.error_code == "DUPLICATE"
        assert dup.data["duplicates"]

    def test_allow_duplicate_overrides(self, cust_conn):
        _create(cust_conn, name="Juan Perez")
        second = _create(cust_conn, name="Juan Perez", allow_duplicate=True)
        assert second.success

    def test_idempotent_on_operation_id(self, cust_conn):
        op = new_uuid()
        first = _create(cust_conn, operation_id=op)
        second = _create(cust_conn, operation_id=op)
        assert first.success and second.success
        assert first.entity_id == second.entity_id

    def test_retries_on_customer_number_collision(self, cust_conn, monkeypatch):
        """CRM-41 (Fase 7): `next_code()` is a read-then-increment — under
        a concurrent writer that already claimed the number, `save()`
        raises a UNIQUE-constraint IntegrityError. The use case must retry
        with a fresh code instead of surfacing the raw DB error."""
        from backend.domain.customers.value_objects.customer_code import CustomerCode
        from backend.infrastructure.db.repositories.customers.customer_repository import (
            CustomerRepository,
        )

        _create(cust_conn, name="Cliente Existente")  # claims CLI-000001

        real_next_code = CustomerRepository.next_code
        calls = {"n": 0}

        def _colliding_then_real(self):
            calls["n"] += 1
            if calls["n"] == 1:
                return CustomerCode.from_sequence(1)  # already taken above
            return real_next_code(self)

        monkeypatch.setattr(CustomerRepository, "next_code", _colliding_then_real)

        result = _create(cust_conn, name="Cliente Nuevo")

        assert result.success, result.error
        assert result.data["code"] != "CLI-000001"
        assert calls["n"] == 2

    def test_gives_up_after_max_attempts_on_persistent_collision(self, cust_conn, monkeypatch):
        from backend.domain.customers.value_objects.customer_code import CustomerCode
        from backend.infrastructure.db.repositories.customers.customer_repository import (
            CustomerRepository,
        )
        import sqlite3

        _create(cust_conn, name="Cliente Existente")  # claims CLI-000001
        monkeypatch.setattr(
            CustomerRepository, "next_code",
            lambda self: CustomerCode.from_sequence(1))  # always colliding

        with pytest.raises(sqlite3.IntegrityError):
            _create(cust_conn, name="Nunca Se Crea")

    def test_invalid_display_name_fails_validation(self, cust_conn):
        result = CreateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", display_name="   ", operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"


class TestLifecycleTransitions:
    def _customer_id(self, conn):
        return _create(conn).entity_id

    def test_suspend_then_activate(self, cust_conn):
        cid = self._customer_id(cust_conn)
        r1 = SuspendCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            reason="mora")
        assert r1.success
        r2 = ActivateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid())
        assert r2.success

    def test_suspend_requires_reason(self, cust_conn):
        cid = self._customer_id(cust_conn)
        result = SuspendCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(), reason="")
        assert not result.success and result.error_code == "VALIDATION"

    def test_deactivate_is_reversible(self, cust_conn):
        """Exact legacy parity: ModuloClientes.eliminar_cliente() equivalent."""
        cid = self._customer_id(cust_conn)
        r1 = DeactivateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid())
        assert r1.success
        r2 = ActivateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid())
        assert r2.success

    def test_close_is_terminal(self, cust_conn):
        cid = self._customer_id(cust_conn)
        closed = CloseCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            reason="cliente solicitó cierre")
        assert closed.success
        reactivate = ActivateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid())
        assert not reactivate.success and reactivate.error_code == "VALIDATION"

    def test_block_requires_reason(self, cust_conn):
        cid = self._customer_id(cust_conn)
        result = BlockCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid())
        assert not result.success and result.error_code == "VALIDATION"

    def test_transition_on_missing_customer_is_not_found(self, cust_conn):
        result = SuspendCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id="does-not-exist",
            operation_id=new_uuid(), reason="x")
        assert not result.success and result.error_code == "NOT_FOUND"


class TestUpdate:
    def test_update_display_name(self, cust_conn):
        cid = _create(cust_conn).entity_id
        result = UpdateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            display_name="Juan Pérez Gómez")
        assert result.success
        row = cust_conn.execute(
            "SELECT display_name, version FROM customers WHERE id=?", (cid,)).fetchone()
        assert row[0] == "Juan Pérez Gómez"
        assert row[1] == 2  # version bumped by record_edit()

    def test_update_rejects_blank_display_name(self, cust_conn):
        cid = _create(cust_conn).entity_id
        result = UpdateCustomerUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            display_name="   ")
        assert not result.success and result.error_code == "VALIDATION"


class TestContacts:
    def test_add_update_set_primary_remove(self, cust_conn):
        cid = _create(cust_conn).entity_id
        added = AddCustomerContactUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, first_name="Maria",
            operation_id=new_uuid(), is_primary=True)
        assert added.success
        contact_id = added.entity_id

        updated = UpdateCustomerContactUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", contact_id=contact_id, operation_id=new_uuid(),
            job_title="Gerente de compras")
        assert updated.success

        second = AddCustomerContactUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, first_name="Luis",
            operation_id=new_uuid())
        set_primary = SetPrimaryCustomerContactUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", contact_id=second.entity_id, operation_id=new_uuid())
        assert set_primary.success
        row = cust_conn.execute(
            "SELECT is_primary FROM customer_contacts WHERE id=?", (contact_id,)).fetchone()
        assert row[0] == 0  # first contact no longer primary

        removed = RemoveCustomerContactUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", contact_id=contact_id, operation_id=new_uuid())
        assert removed.success
        assert cust_conn.execute(
            "SELECT COUNT(*) FROM customer_contacts WHERE id=?", (contact_id,)
        ).fetchone()[0] == 0


class TestAddresses:
    def test_add_update_set_default_remove(self, cust_conn):
        cid = _create(cust_conn).entity_id
        added = AddCustomerAddressUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, street="Av. Reforma",
            operation_id=new_uuid(), is_default=True)
        assert added.success
        address_id = added.entity_id

        updated = UpdateCustomerAddressUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", address_id=address_id, operation_id=new_uuid(),
            postal_code="06600")
        assert updated.success

        second = AddCustomerAddressUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, street="Insurgentes Sur",
            operation_id=new_uuid())
        set_default = SetDefaultCustomerAddressUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", address_id=second.entity_id, operation_id=new_uuid())
        assert set_default.success
        row = cust_conn.execute(
            "SELECT is_default FROM customer_addresses WHERE id=?", (address_id,)).fetchone()
        assert row[0] == 0

        removed = RemoveCustomerAddressUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", address_id=address_id, operation_id=new_uuid())
        assert removed.success


class TestTaxProfile:
    def test_upsert_creates_then_updates(self, cust_conn):
        cid = _create(cust_conn).entity_id
        first = UpdateCustomerTaxProfileUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            tax_identifier="XAXX010101000")
        assert first.success
        second = UpdateCustomerTaxProfileUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            tax_regime="612")
        assert second.success
        assert second.entity_id == first.entity_id  # same profile row, upserted
        row = cust_conn.execute(
            "SELECT tax_identifier, tax_regime FROM customer_tax_profiles WHERE customer_id=?",
            (cid,)).fetchone()
        assert row == ("XAXX010101000", "612")


class TestCustomerProfileQueryService:
    def _service(self, conn, granted):
        class _Checker:
            def has_permission(self, user_id, code):
                return code in granted
        return CustomerProfileQueryService(conn, CustomerDataScopeResolver(_Checker()))

    def test_own_scope_sees_own_customer_only(self, cust_conn):
        owner = "u-vendedor"
        cid = _create(cust_conn, account_owner_user_id=owner).entity_id
        service = self._service(cust_conn, {CustomerPermissions.VIEW_OWN})

        profile = service.get_profile(cid, CustomerScopeContext(user_id=owner))
        assert profile.customer.id == cid

    def test_own_scope_denies_other_owners_customer(self, cust_conn):
        cid = _create(cust_conn, account_owner_user_id="u-vendedor-a").entity_id
        service = self._service(cust_conn, {CustomerPermissions.VIEW_OWN})

        with pytest.raises(CustomerScopeError):
            service.get_profile(cid, CustomerScopeContext(user_id="u-vendedor-b"))

    def test_company_scope_sees_everything(self, cust_conn):
        cid = _create(cust_conn, account_owner_user_id="u-vendedor-a").entity_id
        service = self._service(cust_conn, {CustomerPermissions.VIEW_COMPANY})

        profile = service.get_profile(cid, CustomerScopeContext(user_id="u-auditor"))
        assert profile.customer.id == cid

    def test_profile_includes_children(self, cust_conn):
        cid = _create(cust_conn, account_owner_user_id="u1").entity_id
        AddCustomerContactUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, first_name="Maria",
            operation_id=new_uuid())
        AddCustomerAddressUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, street="Av. Reforma",
            operation_id=new_uuid())
        UpdateCustomerTaxProfileUseCase(_allow_all()).execute(
            cust_conn, actor_user_id="u1", customer_id=cid, operation_id=new_uuid(),
            tax_identifier="XAXX010101000")

        service = self._service(cust_conn, {CustomerPermissions.VIEW_COMPANY})
        profile = service.get_profile(cid, CustomerScopeContext(user_id="u-auditor"))
        assert len(profile.contacts) == 1
        assert len(profile.addresses) == 1
        assert profile.tax_profile is not None

    def test_get_profile_missing_customer_raises_not_found(self, cust_conn):
        service = self._service(cust_conn, {CustomerPermissions.VIEW_COMPANY})
        with pytest.raises(CustomerNotFoundError):
            service.get_profile("does-not-exist", CustomerScopeContext(user_id="u1"))

    def test_list_directory_own_scope_filters_by_owner(self, cust_conn):
        mine = _create(cust_conn, name="Cliente Mio", account_owner_user_id="u1").entity_id
        _create(cust_conn, name="Cliente Ajeno", account_owner_user_id="u2")
        service = self._service(cust_conn, {CustomerPermissions.VIEW_OWN})

        results = service.list_directory(CustomerScopeContext(user_id="u1"))
        assert [c.id for c in results] == [mine]
