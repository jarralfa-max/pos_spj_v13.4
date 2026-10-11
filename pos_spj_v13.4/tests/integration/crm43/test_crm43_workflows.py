"""CRM-43 — flujos del módulo con el presentador REAL y usuarios por rol.

Cada prueba fija un hallazgo de la re-auditoría sobre la base real:
alcance de datos que degeneraba en «sólo lo mío», prospecto sin asignar
invisible, fechas sin zona, ``run(name=...)`` que chocaba, directorio que
ocultaba suspendidos, proyección de ventas desconectada, etc.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from backend.shared.ids import new_uuid
from tests.integration.crm43.conftest import (
    add_branch,
    add_user,
    new_customer,
    presenter_for,
    session_for,
)


def _stage(conn, code):
    return conn.execute("SELECT id FROM crm_stage_definitions WHERE code=?", (code,)).fetchone()[0]


class TestDataScope:
    def test_cashier_sees_only_own_cases_manager_sees_the_branch(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        cashier, cashier_id = presenter_for(conn, "cajero")
        other_cashier, _ = presenter_for(conn, "cajero")
        manager, _ = presenter_for(conn, "gerente")
        mine = cashier.run("create_case", customer_id=customer, case_type="COMPLAINT",
                           subject="Mía", origin_branch_id=cashier.branch_id())
        other_cashier.run("create_case", customer_id=customer, case_type="COMPLAINT",
                          subject="De otro", origin_branch_id=other_cashier.branch_id())
        assert [c.subject for c in cashier.read("cases")] == ["Mía"]
        assert sorted(c.subject for c in manager.read("cases")) == ["De otro", "Mía"]
        assert mine.success

    def test_unassigned_lead_is_visible_to_whoever_created_it(self, conn):
        """CRM-43: un prospecto recién creado no aparecía en NINGÚN directorio."""
        manager, _ = presenter_for(conn, "gerente")
        manager.run("create_lead", display_name="Sin asignar",
                    origin_branch_id=manager.branch_id())
        assert [lead.display_name for lead in manager.read("leads")] == ["Sin asignar"]

    def test_manager_does_not_see_another_branch(self, conn):
        other = add_branch(conn, "Norte")
        manager_north, _ = presenter_for(conn, "gerente", branch=other)
        manager_north.run("create_lead", display_name="Del norte", origin_branch_id=other)
        manager_center, _ = presenter_for(conn, "gerente")
        assert manager_center.read("leads") == []

    def test_customers_are_global_for_every_role(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        new_customer(owner, "Global")
        reader, _ = presenter_for(conn, "solo_lectura")
        assert [r.customer.display_name for r in reader.read("customer_rows")] == ["Global"]


class TestCommercialFlow:
    def test_lead_to_won_opportunity(self, conn):
        manager, manager_id = presenter_for(conn, "gerente")
        lead = manager.run("create_lead", display_name="Restaurante La Pradera",
                           phone_e164="+5213312345678", origin_branch_id=manager.branch_id())
        assert manager.run("assign_lead", lead_id=lead.entity_id,
                           assignee_user_id=manager_id).success
        assert manager.run("mark_lead_contacted", lead_id=lead.entity_id).success
        qualified = manager.run("qualify_lead", lead_id=lead.entity_id, model="BANT_LIKE",
                                criteria={"need": True, "budget": True, "authority": True,
                                          "timeline": False}, min_criteria_passed=3)
        assert qualified.data["decision"] == "QUALIFIED"
        converted = manager.run("convert_lead", lead_id=lead.entity_id)
        assert converted.success, converted.message
        opportunity = manager.run(
            "create_opportunity_from_lead", lead_id=lead.entity_id,
            customer_id=converted.data["customer_id"], amount=Decimal("18500"),
            expected_close_date=date.today() + timedelta(days=20))
        assert opportunity.success, opportunity.message
        moved = manager.run("move_opportunity_stage", opportunity_id=opportunity.entity_id,
                            to_stage_id=_stage(conn, "PROPOSAL"), reason="Propuesta enviada",
                            probability=50, expected_close_date=date.today())
        assert moved.success, moved.message
        rows = manager.read("opportunity_rows")
        assert rows[0].opportunity.weighted_value == Decimal("9250.00")
        assert manager.read("forecast").weighted_pipeline == Decimal("9250")
        assert manager.run("win_opportunity", opportunity_id=opportunity.entity_id,
                           reason="Firmó").success
        insights = manager.read("insights")
        assert insights.opportunities_won == 1 and insights.won_value == Decimal("18500")

    def test_presenter_run_accepts_a_field_called_name(self, conn):
        """``run(self, name, **kw)`` chocaba con los casos de uso que reciben
        ``name`` (oportunidades, segmentos, etapas…)."""
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        assert owner.run("create_opportunity", customer_id=customer, name="Surtido").success
        assert owner.run("create_segment", code="MAYOREO", name="Mayoreo").success

    def test_activity_scheduled_in_utc_is_not_overdue_early(self, conn):
        from datetime import datetime, timezone

        from frontend.desktop.modules.customers_crm.formatting import to_utc_iso

        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        local_in_two_hours = (datetime.now() + timedelta(hours=2)).replace(microsecond=0)
        result = owner.run("create_activity", related_entity_type="CUSTOMER",
                           related_entity_id=customer, activity_type="CALL",
                           subject="Llamar", scheduled_at=to_utc_iso(local_in_two_hours),
                           assigned_user_id=owner_id)
        activity = owner.read("activities_for_user")[0]
        assert result.success and activity.scheduled_at.endswith("+00:00")
        assert activity.effective_status(
            as_of=datetime.now(timezone.utc).isoformat(timespec="seconds")).value == "PLANNED"


class TestPipelineConfiguration:
    def test_create_move_and_retire_a_stage(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        created = owner.run("create_stage", code="DEMO", name="Demostración",
                            probability_default=35)
        assert created.success
        assert owner.run("move_stage", stage_id=created.entity_id, direction=-1).success
        assert owner.run("deactivate_stage", stage_id=created.entity_id).success

    def test_cannot_retire_the_only_won_stage(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        result = owner.run("deactivate_stage", stage_id=_stage(conn, "CLOSED_WON"))
        assert not result.success and "ganada" in result.message

    def test_cannot_retire_a_stage_with_open_opportunities(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        owner.run("create_opportunity", customer_id=customer, name="Abierta",
                  stage_id=_stage(conn, "PROSPECTING"))
        result = owner.run("deactivate_stage", stage_id=_stage(conn, "PROSPECTING"))
        assert not result.success and result.error_code == "STAGE_IN_USE"

    def test_manager_cannot_configure_the_pipeline(self, conn):
        manager, _ = presenter_for(conn, "gerente")
        assert manager.run("create_stage", code="X", name="X").error_code == "PERMISSION_DENIED"


class TestCredit:
    def test_requester_never_approves_own_request(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        manager, _ = presenter_for(conn, "gerente")
        customer = new_customer(owner)
        assert manager.run("request_credit", customer_id=customer,
                           requested_limit=Decimal("5000"), payment_terms_days=15).success
        assert manager.run("review_credit", customer_id=customer, risk_level="LOW").success
        denied = manager.run("approve_credit", customer_id=customer, credit_limit=Decimal("5000"))
        assert not denied.success
        assert owner.run("approve_credit", customer_id=customer,
                         credit_limit=Decimal("4000")).success
        rows = owner.read("credit_rows", statuses=("AUTHORIZED",))
        assert rows[0].summary.credit_limit == "4000"

    def test_cashier_checks_eligibility_with_spanish_reasons(self, conn):
        from backend.application.customer_credit.use_cases.check_credit_sale_eligibility_use_case import (
            CheckCreditSaleEligibilityUseCase,
        )
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.application.customers.session_authorization import (
            CustomerSessionPermissionChecker,
        )
        owner, _ = presenter_for(conn, "system_owner")
        manager, _ = presenter_for(conn, "gerente")
        customer = new_customer(owner)
        manager.run("request_credit", customer_id=customer, requested_limit=Decimal("1000"))
        manager.run("review_credit", customer_id=customer)
        owner.run("approve_credit", customer_id=customer, credit_limit=Decimal("1000"))
        cashier_id = add_user(conn, "cajero")
        policy = CustomerAuthorizationPolicy(CustomerSessionPermissionChecker(
            session_for(conn, cashier_id, "cajero")))
        ok = CheckCreditSaleEligibilityUseCase(policy).execute(
            conn, actor_user_id=cashier_id, customer_id=customer, amount="300",
            operation_id=new_uuid())
        too_much = CheckCreditSaleEligibilityUseCase(policy).execute(
            conn, actor_user_id=cashier_id, customer_id=customer, amount="5000",
            operation_id=new_uuid())
        assert ok.success
        assert too_much.data["violations"] == [
            "Crédito insuficiente: disponible $1,000.00, requerido $5,000.00."]


class TestPrivacyAndExports:
    def test_contact_data_is_masked_by_permission(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        owner.run("add_contact", customer_id=customer, first_name="Ana",
                  phone_e164="+5213398765432", email="ana@x.mx")
        cashier, _ = presenter_for(conn, "cajero")
        reader, _ = presenter_for(conn, "solo_lectura")
        manager, _ = presenter_for(conn, "gerente")
        phone = lambda p: p.read("customer_profile", customer_id=customer).profile.contacts[0].phone_e164  # noqa: E731
        assert phone(manager) == "+5213398765432"
        assert phone(cashier).endswith("5432") and phone(cashier).startswith("•")
        assert "5432" not in phone(reader)

    def test_export_masks_by_default_and_is_audited(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        owner.run("add_contact", customer_id=customer, first_name="Ana", is_primary=True,
                  phone_e164="+5213398765432")
        result = owner.run("export_data", dataset="customers")
        table = result.data["table"]
        assert "id" not in [h.lower() for h in table.headers]
        assert "5432" not in table.rows[0][7]
        assert owner.read("exports_history")[0]["action"] == "CUSTOMER_DATA_EXPORTED"

    def test_sensitive_export_requires_reason_and_permission(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        manager, _ = presenter_for(conn, "gerente")
        assert owner.run("export_data", dataset="customers",
                         include_sensitive=True).error_code == "VALIDATION"
        assert manager.run("export_data", dataset="customers", include_sensitive=True,
                           reason="auditoría").error_code == "PERMISSION_DENIED"

    def test_anonymization_needs_a_second_person(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        other_owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Pide borrado")
        request = owner.run("create_privacy_request", customer_id=customer,
                            request_type="ANONYMIZATION")
        owner.run("validate_privacy_request", request_id=request.entity_id)
        owner.run("process_privacy_request", request_id=request.entity_id)
        assert not owner.run("anonymize_customer", request_id=request.entity_id,
                             reason="ARCO").success
        assert other_owner.run("anonymize_customer", request_id=request.entity_id,
                               reason="ARCO").success


class TestCustomerMaster:
    def test_directory_keeps_suspended_customers(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        assert owner.run("suspend_customer", customer_id=customer, reason="Adeudo").success
        statuses = [r.customer.status.value for r in owner.read("customer_rows")]
        assert statuses == ["SUSPENDED"]

    def test_commercial_account_create_and_update(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, customer_type="BUSINESS")
        account = owner.run("create_account", customer_id=customer, account_type="RESTAURANT",
                            industry="Comida", company_size="SMALL")
        assert account.success
        assert owner.run("update_account", account_id=account.entity_id,
                         website="https://x.mx", status="INACTIVE").success
        accounts = owner.read("customer_profile", customer_id=customer).profile.accounts
        assert (accounts[0].website, accounts[0].status) == ("https://x.mx", "INACTIVE")

    def test_lookup_finds_by_customer_code(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Por código")
        code = conn.execute("SELECT customer_number FROM customers WHERE id=?",
                            (customer,)).fetchone()[0]
        assert [o.id for o in owner.customer_search_options(code)] == [customer]


class TestSalesProjectionWiring:
    def test_completed_and_reversed_sales_reach_the_customer(self, conn):
        from backend.application.customers.integrations.sales_wiring import wire_customers_sales

        class _Bus:
            def __init__(self):
                self.handlers = {}

            def subscribe(self, event, handler, **_kw):
                self.handlers.setdefault(event, []).append(handler)

            def publish(self, event, envelope):
                for handler in self.handlers.get(event, []):
                    handler(envelope)

        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        bus = _Bus()
        assert wire_customers_sales(bus, conn)["count"] == 2
        sale = {"event_id": new_uuid(), "timestamp": "2026-10-08T20:00:00+00:00",
                "payload": {"customer_id": customer}}
        bus.publish("SALE_COMPLETED", sale)
        bus.publish("SALE_COMPLETED", sale)  # idempotente por event_id
        assert conn.execute("SELECT purchase_count FROM customers WHERE id=?",
                            (customer,)).fetchone()[0] == 1
        bus.publish("SALE_REVERSED", {"event_id": new_uuid(), "payload": {"customer_id": customer}})
        assert conn.execute("SELECT purchase_count FROM customers WHERE id=?",
                            (customer,)).fetchone()[0] == 0

    def test_startup_wiring_includes_customers(self):
        import inspect

        from backend.bootstrap.wiring import event_wiring
        assert "wire_customers_sales" in inspect.getsource(event_wiring.wire_cross_context_events)


class TestServiceCases:
    def test_first_response_status_is_tracked_apart_from_resolution(self, conn):
        manager, manager_id = presenter_for(conn, "gerente")
        customer = new_customer(manager)
        case = manager.run("create_case", customer_id=customer, case_type="COMPLAINT",
                           subject="Caso", priority="HIGH", origin_branch_id=manager.branch_id())
        manager.run("assign_case", case_id=case.entity_id, assignee_user_id=manager_id)
        manager.run("start_case", case_id=case.entity_id)
        assert manager.run("first_response_case", case_id=case.entity_id).success
        detail = manager.read("case_detail", case_id=case.entity_id)
        assert detail.sla.first_response_status().value == "COMPLETED"
        assert detail.sla.effective_breach_status().value == "ON_TIME"
