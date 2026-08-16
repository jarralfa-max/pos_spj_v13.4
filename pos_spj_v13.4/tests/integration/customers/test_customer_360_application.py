"""CRM-12 — QueryServices/Customer 360 application tests: cross-context
history timeline, fast lookup, CRM calendar, and the Customer360QueryService
aggregator (including graceful per-section degradation).
"""

from __future__ import annotations

import pytest

from backend.application.crm.authorization import CRMAuthorizationPolicy
from backend.application.crm.data_scope import CRMDataScopeResolver, CRMScopeContext
from backend.application.crm.queries.crm_calendar_query_service import CRMCalendarQueryService
from backend.application.crm.queries.opportunity_directory_query_service import (
    OpportunityDirectoryQueryService,
)
from backend.application.crm.use_cases.activity_use_cases import CreateCRMActivityUseCase
from backend.application.crm.use_cases.note_use_cases import CreateCRMNoteUseCase
from backend.application.crm.use_cases.opportunity_use_cases import CreateOpportunityUseCase
from backend.application.crm.use_cases.task_use_cases import CreateCRMTaskUseCase
from backend.application.customer_service.queries.service_case_query_service import (
    ServiceCaseQueryService,
)
from backend.application.customer_service.use_cases.service_case_use_cases import (
    AssignServiceCaseUseCase,
    CreateServiceCaseUseCase,
)
from backend.application.customers.authorization import CustomerAuthorizationPolicy
from backend.application.customers.data_scope import CustomerDataScopeResolver
from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.queries.customer_360_query_service import (
    Customer360QueryService,
)
from backend.application.customers.queries.customer_history_query_service import (
    CustomerHistoryQueryService,
)
from backend.application.customers.queries.customer_lookup_query_service import (
    CustomerLookupQueryService,
)
from backend.application.customers.use_cases.lifecycle_use_cases import CreateCustomerUseCase
from backend.domain.crm.entities.stage_definition import CRMStageDefinition
from backend.domain.crm.enums import CRMActivityType, CRMRelatedEntityType
from backend.domain.crm.exceptions import CRMDomainError
from backend.domain.customers.exceptions import CustomerDomainError, CustomerScopeError
from backend.infrastructure.db.repositories.crm.unit_of_work import CRMUnitOfWork
from backend.shared.ids import new_uuid


class _AllowAllChecker:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return True


class _DenyChecker:
    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return False


class _SelectiveChecker:
    def __init__(self, denied: set[str]) -> None:
        self._denied = denied

    def has_permission(self, user_id: str, permission_code: str) -> bool:
        return permission_code not in self._denied


def _allow_cust():
    return CustomerAuthorizationPolicy(_AllowAllChecker())


def _allow_crm():
    return CRMAuthorizationPolicy(_AllowAllChecker())


def _customer_scope_resolver(checker=None):
    return CustomerDataScopeResolver(checker or _AllowAllChecker())


def _crm_scope_resolver(checker=None):
    return CRMDataScopeResolver(checker or _AllowAllChecker())


def _customer(conn, *, name="Restaurante El Sol") -> str:
    result = CreateCustomerUseCase(_allow_cust()).execute(
        conn, actor_user_id="u1", display_name=name, operation_id=new_uuid())
    assert result.success
    return result.entity_id


def _stage_id(conn) -> str:
    with CRMUnitOfWork(conn) as uow:
        stage = CRMStageDefinition.create("PROSPECTING", "Prospección", 1)
        uow.stage_definitions.save(stage)
    return stage.id


def _opportunity(conn, customer_id, *, owner="u-vendedor") -> str:
    result = CreateOpportunityUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", customer_id=customer_id, name="Oportunidad de prueba",
        operation_id=new_uuid(), stage_id=_stage_id(conn), owner_user_id=owner)
    assert result.success
    return result.entity_id


def _service_case(conn, customer_id, *, assignee="u-agente") -> str:
    result = CreateServiceCaseUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", customer_id=customer_id, case_type="QUESTION",
        subject="Consulta de prueba", operation_id=new_uuid())
    assert result.success
    AssignServiceCaseUseCase(_allow_crm()).execute(
        conn, actor_user_id="u1", case_id=result.entity_id, assignee_user_id=assignee,
        operation_id=new_uuid())
    return result.entity_id


class TestCustomerHistoryQueryService:
    def test_aggregates_customers_and_opportunity_audit_entries(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        _opportunity(full_crm_conn, customer_id)

        history = CustomerHistoryQueryService(full_crm_conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        modules = {e.source_module for e in history}
        assert "customers" in modules
        assert "crm" in modules

    def test_requires_permission(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        service = CustomerHistoryQueryService(full_crm_conn,
                                              CustomerAuthorizationPolicy(_DenyChecker()))
        with pytest.raises(CustomerDomainError):
            service.get_timeline(customer_id, actor_user_id="u1")

    def test_sorted_most_recent_first(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        _opportunity(full_crm_conn, customer_id)
        history = CustomerHistoryQueryService(full_crm_conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        occurred = [e.occurred_at for e in history]
        assert occurred == sorted(occurred, reverse=True)

    def test_unrelated_opportunity_not_included(self, full_crm_conn):
        customer_a = _customer(full_crm_conn, name="Cliente A")
        customer_b = _customer(full_crm_conn, name="Cliente B")
        _opportunity(full_crm_conn, customer_b)

        history = CustomerHistoryQueryService(full_crm_conn, _allow_cust()).get_timeline(
            customer_a, actor_user_id="u1")
        assert all(e.source_module != "crm" for e in history)

    def test_includes_sales_bridged_via_legacy_customer_id(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            ResolveLegacyCustomerUseCase,
        )

        legacy_id = new_uuid()
        conn.execute(
            "INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente Legacy', 1)",
            (legacy_id,))
        customer_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id=legacy_id)
        conn.execute(
            "INSERT INTO ventas (id, folio, cliente_id, total, estado, usuario)"
            " VALUES (?, 'F-100', ?, 750.0, 'completada', 'cajero1')",
            (new_uuid(), legacy_id))
        conn.commit()

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        sales = [e for e in history if e.source_module == "ventas"]
        assert len(sales) == 1
        assert sales[0].action == "VENTA_COMPLETADA"
        assert "F-100" in sales[0].reason
        assert sales[0].actor_user_id == "cajero1"

    def test_cancelled_sale_uses_cancelled_action(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            ResolveLegacyCustomerUseCase,
        )

        legacy_id = new_uuid()
        conn.execute(
            "INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente Legacy', 1)",
            (legacy_id,))
        customer_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id=legacy_id)
        conn.execute(
            "INSERT INTO ventas (id, folio, cliente_id, total, estado)"
            " VALUES (?, 'F-101', ?, 100.0, 'cancelada')",
            (new_uuid(), legacy_id))
        conn.commit()

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        sales = [e for e in history if e.source_module == "ventas"]
        assert sales[0].action == "VENTA_CANCELADA"

    def test_no_legacy_bridge_contributes_no_sales(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = _customer(conn, name="Cliente Nativo")

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        assert all(e.source_module != "ventas" for e in history)

    def test_includes_activity_directly_related_to_customer(self, full_crm_conn):
        conn = full_crm_conn
        customer_id = _customer(conn)
        result = CreateCRMActivityUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", activity_type="CALL", related_entity_type="CUSTOMER",
            related_entity_id=customer_id, subject="Llamada de seguimiento",
            operation_id=new_uuid())
        assert result.success

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        crm_direct = [e for e in history if e.source_entity_id == result.entity_id]
        assert len(crm_direct) == 1
        assert crm_direct[0].action == "CRM_ACTIVITY_CREATED"

    def test_includes_task_directly_related_to_customer(self, full_crm_conn):
        conn = full_crm_conn
        customer_id = _customer(conn)
        result = CreateCRMTaskUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id=customer_id, title="Enviar cotización",
            due_at="2026-09-01T00:00:00+00:00", operation_id=new_uuid())
        assert result.success

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        crm_direct = [e for e in history if e.source_entity_id == result.entity_id]
        assert len(crm_direct) == 1

    def test_includes_note_directly_related_to_customer(self, full_crm_conn):
        conn = full_crm_conn
        customer_id = _customer(conn)
        result = CreateCRMNoteUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", related_entity_type="CUSTOMER",
            related_entity_id=customer_id, body="Cliente prefiere entrega por la tarde",
            operation_id=new_uuid())
        assert result.success

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        crm_direct = [e for e in history if e.source_entity_id == result.entity_id]
        assert len(crm_direct) == 1
        assert crm_direct[0].action == "CRM_NOTE_CREATED"

    def test_activity_for_a_different_customer_not_included(self, full_crm_conn):
        conn = full_crm_conn
        customer_a = _customer(conn, name="Cliente A")
        customer_b = _customer(conn, name="Cliente B")
        CreateCRMActivityUseCase(_allow_crm()).execute(
            conn, actor_user_id="u1", activity_type="CALL", related_entity_type="CUSTOMER",
            related_entity_id=customer_b, subject="Llamada", operation_id=new_uuid())

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_a, actor_user_id="u1")
        assert all(e.action != "ACTIVITY_CREATED" for e in history)

    def test_includes_whatsapp_order_bridged_via_legacy_customer_id(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        from backend.application.customers.use_cases.legacy_customer_bridge_use_cases import (
            ResolveLegacyCustomerUseCase,
        )

        legacy_id = new_uuid()
        conn.execute(
            "INSERT INTO clientes (id, nombre, activo) VALUES (?, 'Cliente WA', 1)",
            (legacy_id,))
        customer_id = ResolveLegacyCustomerUseCase().execute(conn, legacy_customer_id=legacy_id)
        conn.execute(
            "INSERT INTO pedidos_whatsapp (id, numero_whatsapp, cliente_id, estado, total)"
            " VALUES (?, '+525500000000', ?, 'nuevo', 350.0)",
            (new_uuid(), legacy_id))
        conn.commit()

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        wa_entries = [e for e in history if e.source_module == "whatsapp"]
        assert len(wa_entries) == 1
        assert wa_entries[0].action == "PEDIDO_WHATSAPP"
        assert "350" in wa_entries[0].reason

    def test_no_legacy_bridge_contributes_no_whatsapp_orders(self, full_crm_conn_with_ops):
        conn = full_crm_conn_with_ops
        customer_id = _customer(conn, name="Cliente Nativo WA")

        history = CustomerHistoryQueryService(conn, _allow_cust()).get_timeline(
            customer_id, actor_user_id="u1")
        assert all(e.source_module != "whatsapp" for e in history)


class TestCustomerLookupQueryService:
    def test_lookup_by_name_fragment(self, full_crm_conn):
        _customer(full_crm_conn, name="Juan Perez Gomez")
        results = CustomerLookupQueryService(full_crm_conn, _allow_cust()).lookup(
            "Perez", actor_user_id="u1")
        assert len(results) == 1
        assert results[0].display_name == "Juan Perez Gomez"

    def test_empty_query_returns_nothing(self, full_crm_conn):
        _customer(full_crm_conn, name="Juan Perez Gomez")
        results = CustomerLookupQueryService(full_crm_conn, _allow_cust()).lookup(
            "   ", actor_user_id="u1")
        assert results == []

    def test_requires_permission(self, full_crm_conn):
        _customer(full_crm_conn, name="Juan Perez Gomez")
        service = CustomerLookupQueryService(full_crm_conn,
                                             CustomerAuthorizationPolicy(_DenyChecker()))
        with pytest.raises(CustomerDomainError):
            service.lookup("Juan", actor_user_id="u1")


class TestCRMCalendarQueryService:
    def test_filters_by_date_range(self, full_crm_conn):
        CreateCRMActivityUseCase(_allow_crm()).execute(
            full_crm_conn, actor_user_id="u1", activity_type=CRMActivityType.CALL.value,
            related_entity_type=CRMRelatedEntityType.CUSTOMER.value, related_entity_id="cust-1",
            subject="Llamar", operation_id=new_uuid(), assigned_user_id="u-vendedor",
            scheduled_at="2026-09-01T10:00:00+00:00")
        CreateCRMTaskUseCase(_allow_crm()).execute(
            full_crm_conn, actor_user_id="u1",
            related_entity_type=CRMRelatedEntityType.CUSTOMER.value, related_entity_id="cust-1",
            title="Enviar cotización", due_at="2026-09-15T00:00:00+00:00",
            operation_id=new_uuid(), assigned_user_id="u-vendedor")

        entries = CRMCalendarQueryService(full_crm_conn, _allow_crm()).get_calendar(
            "u-vendedor", actor_user_id="u1", start_date="2026-09-01", end_date="2026-09-01")
        assert len(entries) == 1
        assert entries[0].entry_type == "ACTIVITY"

    def test_requires_both_permissions(self, full_crm_conn):
        service = CRMCalendarQueryService(full_crm_conn, CRMAuthorizationPolicy(_DenyChecker()))
        with pytest.raises(CRMDomainError):
            service.get_calendar("u1", actor_user_id="u1", start_date="2026-01-01",
                                 end_date="2026-12-31")


class TestCustomer360QueryService:
    def _service(self, conn, checker=None):
        checker = checker or _AllowAllChecker()
        return Customer360QueryService(
            conn, _customer_scope_resolver(checker), _crm_scope_resolver(checker),
            CustomerAuthorizationPolicy(checker), CRMAuthorizationPolicy(checker))

    def test_full_aggregation_happy_path(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        _opportunity(full_crm_conn, customer_id, owner="u1")
        _service_case(full_crm_conn, customer_id, assignee="u1")

        view = self._service(full_crm_conn).get_360(
            customer_id, actor_user_id="u1", team_member_ids=("u1", "u-vendedor"))

        assert view.profile.customer.id == customer_id
        assert len(view.open_opportunities) == 1
        assert len(view.open_cases) == 1
        assert view.credit_summary is not None
        assert view.recent_history

    def test_unknown_customer_raises(self, full_crm_conn):
        service = self._service(full_crm_conn)
        with pytest.raises(CustomerDomainError):
            service.get_360("does-not-exist", actor_user_id="u1")

    def test_denied_customer_scope_raises(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        checker = _SelectiveChecker(denied={
            CustomerPermissions.VIEW, CustomerPermissions.VIEW_OWN,
            CustomerPermissions.VIEW_TEAM, CustomerPermissions.VIEW_BRANCH,
            CustomerPermissions.VIEW_TERRITORY, CustomerPermissions.VIEW_PORTFOLIO,
            CustomerPermissions.VIEW_COMPANY})
        service = self._service(full_crm_conn, checker)
        with pytest.raises(CustomerScopeError):
            service.get_360(customer_id, actor_user_id="u1")

    def test_missing_section_permission_degrades_gracefully(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        checker = _SelectiveChecker(denied={CustomerPermissions.CREDIT_VIEW})
        view = self._service(full_crm_conn, checker).get_360(customer_id, actor_user_id="u1")
        assert view.profile.customer.id == customer_id
        assert view.credit_summary is None


class TestOpportunityAndServiceCaseListForCustomer:
    def test_opportunity_list_for_customer_scope_filtered(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        _opportunity(full_crm_conn, customer_id, owner="u-vendedor")

        service = OpportunityDirectoryQueryService(full_crm_conn, _crm_scope_resolver())
        result = service.list_for_customer(
            customer_id, CRMScopeContext(user_id="u1", team_member_ids=("u-vendedor",)))
        assert len(result) == 1

    def test_service_case_list_for_customer_masks_sensitive(self, full_crm_conn):
        customer_id = _customer(full_crm_conn)
        _service_case(full_crm_conn, customer_id)

        service = ServiceCaseQueryService(full_crm_conn, _crm_scope_resolver(), _allow_crm())
        result = service.list_for_customer(
            customer_id, CRMScopeContext(user_id="u1", team_member_ids=("u-agente",)))
        assert len(result) == 1
