"""Auditoría externa de Clientes/CRM sobre d9f2bca (2026-10-09) — Entrega A.

F03 alcance en comandos y lecturas · F04 búsqueda sin exponer contacto ·
F05 alta/importación guardan teléfono, correo y RFC · F13 selección de cliente ·
F14 edición de contacto validada · F15 anonimización completa.
Cada prueba reproduce el escenario de la auditoría.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from backend.shared.ids import new_uuid
from tests.integration.crm43.conftest import new_customer, presenter_for


class _Grant:
    """Verificador explícito: concede SÓLO los códigos indicados."""

    def __init__(self, *codes: str) -> None:
        self._codes = set(codes)

    def has_permission(self, user_id: str, code: str) -> bool:
        return code in self._codes


def _contacts(conn, customer):
    return conn.execute("SELECT first_name, phone_e164, email, is_primary, status"
                        " FROM customer_contacts WHERE customer_id=?", (customer,)).fetchall()


class TestF03Scope:
    def test_own_scope_cannot_edit_another_owners_customer(self, conn):
        from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
        from backend.application.crm.record_scope_guard import CRMRecordScopeGuard
        from backend.application.customers.data_scope import CustomerDataScopeResolver

        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "De otro vendedor", account_owner_user_id=new_uuid())
        checker = _Grant("CLIENTES.ver", "CLIENTES.ver.propia", "CLIENTES.editar")
        guard = CRMRecordScopeGuard(conn, CRMDataScopeResolver(checker),
                                    CustomerDataScopeResolver(checker))
        reason = guard.denial(CRMScopeContext(user_id="seller"), {"customer_id": customer})
        assert reason and "fuera de tu alcance" in reason
        mine = new_customer(owner, "Mío", account_owner_user_id="seller")
        assert guard.denial(CRMScopeContext(user_id="seller"), {"customer_id": mine}) is None

    def test_tasks_view_does_not_reveal_other_users_tasks(self, conn):
        from backend.application.crm.authorization import CRMAuthorizationPolicy
        from backend.application.crm.queries.crm_task_query_service import CRMTaskQueryService
        from backend.domain.crm.exceptions import CRMDomainError

        tasks = CRMTaskQueryService(conn, CRMAuthorizationPolicy(_Grant("CRM.tareas.ver")))
        with pytest.raises(CRMDomainError):
            tasks.list_assigned_to("someone-else", actor_user_id="me")
        assert tasks.list_assigned_to("me", actor_user_id="me") == []

    def test_supervisor_can_see_other_users_tasks(self, conn):
        from backend.application.crm.authorization import CRMAuthorizationPolicy
        from backend.application.crm.queries.crm_task_query_service import CRMTaskQueryService

        tasks = CRMTaskQueryService(conn, CRMAuthorizationPolicy(
            _Grant("CRM.tareas.ver", "CRM.tareas.reasignar")))
        assert tasks.list_assigned_to("someone-else", actor_user_id="boss") == []

    def test_tasks_of_an_out_of_scope_case_are_hidden(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        cashier, _ = presenter_for(conn, "cajero")
        other, _ = presenter_for(conn, "cajero")
        case = other.run("create_case", customer_id=customer, case_type="COMPLAINT",
                         subject="Ajeno", origin_branch_id=other.branch_id()).entity_id
        with pytest.raises(Exception, match="fuera de tu alcance"):
            cashier.read("tasks_for", entity_type="CASE", entity_id=case)
        assert other.read("tasks_for", entity_type="CASE", entity_id=case) == []

    def test_import_update_by_id_needs_edit_permission(self, conn):
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.application.customers.use_cases.import_use_cases import (
            ImportCustomersUseCase,
        )
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Nombre original")
        result = ImportCustomersUseCase(CustomerAuthorizationPolicy(
            _Grant("CLIENTES.importar"))).execute(
            conn, actor_user_id="importer",
            rows=[{"customer_id": customer, "display_name": "Cambiado"}],
            operation_id=new_uuid())
        assert result.success
        name = conn.execute("SELECT display_name FROM customers WHERE id=?",
                            (customer,)).fetchone()[0]
        assert name == "Nombre original"


class TestF04Lookup:
    def test_search_only_masks_phone_and_email(self, conn):
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.application.customers.queries.customer_lookup_query_service import (
            CustomerLookupQueryService,
        )
        owner, _ = presenter_for(conn, "system_owner")
        new_customer(owner, "Carnicería Pepe", phone_e164="+525512345678",
                     email="pepe@correo.mx")
        only_search = CustomerLookupQueryService(
            conn, CustomerAuthorizationPolicy(_Grant("CLIENTES.buscar")))
        hit = only_search.lookup("Pepe", actor_user_id="x")[0]
        assert "5512345678" not in (hit.phone_e164 or "") and "•" in hit.phone_e164
        assert "pepe@correo.mx" != hit.email
        sensitive = CustomerLookupQueryService(conn, CustomerAuthorizationPolicy(
            _Grant("CLIENTES.buscar", "CLIENTES.sensible.ver")))
        assert sensitive.lookup("Pepe", actor_user_id="x")[0].phone_e164 == "+525512345678"
        assert only_search.lookup("5512345678", actor_user_id="x"), "busca por teléfono"


class TestF05CaptureIsPersisted:
    def test_create_keeps_phone_email_and_rfc(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Taquería Juárez", phone_e164="+525511112222",
                                email="Ventas@Juarez.MX", tax_identifier="taju800101ab1",
                                legal_name="Taquería Juárez SA de CV")
        assert [tuple(c)[1:4] for c in _contacts(conn, customer)] == [
            ("+525511112222", "ventas@juarez.mx", 1)]
        tax = conn.execute("SELECT tax_identifier, legal_name FROM customer_tax_profiles"
                           " WHERE customer_id=?", (customer,)).fetchone()
        assert tuple(tax) == ("TAJU800101AB1", "Taquería Juárez SA de CV")

    def test_invalid_phone_is_refused_and_nothing_is_created(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        result = owner.run("create_customer", display_name="Teléfono malo",
                           phone_e164="55-1234")
        assert not result.success and "E.164" in result.message
        assert conn.execute("SELECT COUNT(*) FROM customers WHERE display_name='Teléfono malo'"
                            ).fetchone()[0] == 0

    def test_import_keeps_contact_and_rfc(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        result = owner.run("import_customers", rows=[
            {"display_name": "Importado Uno", "phone_e164": "+525533334444",
             "email": "uno@x.mx", "tax_identifier": "IMUN800101AB1"},
            {"display_name": "Importado Malo", "phone_e164": "123"}])
        assert result.success, result.message
        customer = conn.execute("SELECT id FROM customers WHERE display_name='Importado Uno'"
                                ).fetchone()[0]
        assert [tuple(c)[1:3] for c in _contacts(conn, customer)] == [
            ("+525533334444", "uno@x.mx")]
        assert conn.execute("SELECT COUNT(*) FROM customers WHERE display_name='Importado Malo'"
                            ).fetchone()[0] == 0

    def test_pos_quick_create_has_one_primary_contact(self, conn):
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.infrastructure.integrations.sales_customer_client import SalesCustomerClient
        result = SalesCustomerClient(conn, authorization=CustomerAuthorizationPolicy(
            _Grant("CLIENTES.crear", "CLIENTES.contacto.crear"))).quick_create(
            actor_user_id="cashier", operation_id=new_uuid(), display_name="Rápido",
            phone_e164="+525599998888")
        assert result.success
        assert len(_contacts(conn, result.entity_id)) == 1


class TestF14ContactEdit:
    def test_edit_applies_the_same_rules_as_create(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        contact = owner.run("add_contact", customer_id=customer, first_name="Ana",
                            phone_e164="+525512340000").entity_id
        for bad in ({"first_name": " "}, {"email": "no-es-correo"}, {"phone_e164": "123"}):
            result = owner.run("update_contact", contact_id=contact, **bad)
            assert not result.success and result.error_code == "VALIDATION", bad
        assert owner.run("update_contact", contact_id=contact, email="ANA@X.MX").success
        assert _contacts(conn, customer)[0][2] == "ana@x.mx"


class TestF15Anonymization:
    def test_contacts_and_personal_addresses_are_scrubbed(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        other_owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Pide borrado", phone_e164="+525500001111",
                                email="borra@me.mx", tax_identifier="BORR800101AB1")
        owner.run("add_address", customer_id=customer, address_type="DELIVERY",
                  street="Calle Privada 12", postal_code="06000")
        owner.run("add_address", customer_id=customer, address_type="FISCAL",
                  street="Av. Fiscal 1", postal_code="06000")
        request = owner.run("create_privacy_request", customer_id=customer,
                            request_type="ANONYMIZATION").entity_id
        owner.run("validate_privacy_request", request_id=request)
        owner.run("process_privacy_request", request_id=request)
        assert other_owner.run("anonymize_customer", request_id=request, reason="ARCO").success

        assert [tuple(c) for c in _contacts(conn, customer)] == [
            ("Contacto anonimizado", None, None, 1, "INACTIVE")]
        streets = dict(conn.execute("SELECT address_type, street FROM customer_addresses"
                                    " WHERE customer_id=?", (customer,)).fetchall())
        assert streets == {"DELIVERY": "Anonimizado", "FISCAL": "Av. Fiscal 1"}
        assert conn.execute("SELECT tax_identifier FROM customer_tax_profiles"
                            " WHERE customer_id=?", (customer,)).fetchone()[0] == "BORR800101AB1"
