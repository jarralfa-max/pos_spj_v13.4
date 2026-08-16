"""CRM-41 (Fase 7, Base de datos) — duplicate detection uses SQL blocking
keys instead of loading every customer, and normalized_name/
normalized_legal_name stay in sync with display_name/legal_name."""

from __future__ import annotations

from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.use_cases.contact_use_cases import AddCustomerContactUseCase
from backend.application.customers.use_cases.lifecycle_use_cases import (
    CreateCustomerUseCase,
    UpdateCustomerUseCase,
)
from backend.application.customers.use_cases.tax_profile_use_cases import (
    UpdateCustomerTaxProfileUseCase,
)
from backend.infrastructure.db.repositories.customers.unit_of_work import CustomerUnitOfWork
from backend.shared.ids import new_uuid


def _allow():
    return CustomerAuthorizationPolicy.permissive_for_tests()


def _create(conn, *, name="Juan Perez", **kwargs):
    return CreateCustomerUseCase(_allow()).execute(
        conn, actor_user_id="u1", display_name=name, operation_id=new_uuid(), **kwargs)


def _add_contact(conn, customer_id, *, phone_e164=None, email=None):
    return AddCustomerContactUseCase(_allow()).execute(
        conn, actor_user_id="u1", customer_id=customer_id, first_name="Contacto",
        operation_id=new_uuid(), phone_e164=phone_e164, email=email, is_primary=True)


def _set_tax_identifier(conn, customer_id, tax_identifier):
    return UpdateCustomerTaxProfileUseCase(_allow()).execute(
        conn, actor_user_id="u1", customer_id=customer_id, operation_id=new_uuid(),
        tax_identifier=tax_identifier)


class TestFindDuplicateRowsMatching:
    def test_no_blocking_keys_returns_nothing(self, cust_conn):
        _create(cust_conn, name="Cliente Existente")
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching()
        assert rows == []

    def test_matches_by_normalized_display_name(self, cust_conn):
        _create(cust_conn, name="José Pérez")
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            normalized_display_name="joseperez")
        assert len(rows) == 1

    def test_matches_candidate_display_name_against_stored_legal_name(self, cust_conn):
        """The original full-scan policy checks the candidate's display
        name against BOTH the stored display name AND legal name — the
        SQL blocking filter must preserve that, not just display-vs-display."""
        _create(cust_conn, name="Distribuidora XYZ", legal_name="Juan Perez Comercializadora")
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            normalized_display_name="juanperezcomercializadora")
        assert len(rows) == 1

    def test_matches_by_phone(self, cust_conn):
        result = _create(cust_conn, name="Con Telefono")
        assert result.success
        assert _add_contact(cust_conn, result.entity_id, phone_e164="+525512345678").success
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            phone_e164="+525512345678")
        assert len(rows) == 1

    def test_matches_by_email_case_insensitive(self, cust_conn):
        result = _create(cust_conn, name="Con Correo")
        assert _add_contact(cust_conn, result.entity_id, email="Cliente@Example.com").success
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            email="cliente@example.com")
        assert len(rows) == 1

    def test_matches_by_tax_identifier_case_insensitive(self, cust_conn):
        result = _create(cust_conn, name="Con RFC")
        assert _set_tax_identifier(cust_conn, result.entity_id, "xaxx010101000").success
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            tax_identifier="XAXX010101000")
        assert len(rows) == 1

    def test_unrelated_customer_not_returned(self, cust_conn):
        _create(cust_conn, name="Alguien Mas")
        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            normalized_display_name="nombrequenoexiste")
        assert rows == []


class TestNormalizedNameStaysInSync:
    def test_update_recomputes_normalized_name(self, cust_conn):
        result = _create(cust_conn, name="Nombre Original")
        UpdateCustomerUseCase(_allow()).execute(
            cust_conn, actor_user_id="u1", customer_id=result.entity_id,
            operation_id=new_uuid(), display_name="Nombre Cambiado")

        rows = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            normalized_display_name="nombrecambiado")
        assert len(rows) == 1
        stale = CustomerUnitOfWork(cust_conn).customers.find_duplicate_rows_matching(
            normalized_display_name="nombreoriginal")
        assert stale == []


class TestCreateCustomerStillDetectsDuplicatesViaBlockingKeys:
    def test_end_to_end_duplicate_still_rejected(self, cust_conn):
        _create(cust_conn, name="Cliente Repetido", phone_e164="+525500001111")
        second = _create(cust_conn, name="Cliente Repetido", phone_e164="+525500001111")
        assert not second.success
        assert second.error_code == "DUPLICATE"

    def test_unrelated_new_customer_not_blocked(self, cust_conn):
        _create(cust_conn, name="Cliente Uno")
        second = _create(cust_conn, name="Cliente Completamente Distinto")
        assert second.success
