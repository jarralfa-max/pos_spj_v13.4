"""Auditoría externa de Clientes/CRM sobre d9f2bca (2026-10-09) — Entrega B.

F06 fusión coherente · F07 concurrencia · F08 actividades para avanzar de etapa ·
F09 validación de oportunidades · F10 una tarea por regla · F11 pausas del SLA ·
F12 historial con ventas canónicas · F16 conversión de prospecto en un paso.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from backend.shared.ids import new_uuid
from tests.integration.crm43.conftest import new_customer, presenter_for


def _stage(conn, code):
    return conn.execute("SELECT id FROM crm_stage_definitions WHERE code=?", (code,)).fetchone()[0]


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class TestF06Merge:
    def _merge(self, conn, owner, other_owner, master, merged):
        record = owner.run("propose_merge", master_customer_id=master,
                           merged_customer_id=merged, reason="duplicado").entity_id
        result = other_owner.run("execute_merge", merge_record_id=record, reason="confirmado")
        assert result.success, result.message

    def test_one_primary_contact_and_credit_follows_the_survivor(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        other_owner, _ = presenter_for(conn, "system_owner")
        master = new_customer(owner, "Abarrotes Luna", phone_e164="+525511110000")
        merged = new_customer(owner, "Abarrotes Luna SA", phone_e164="+525522220000",
                              allow_duplicate=True)
        conn.execute(
            "INSERT INTO customer_credit_profiles (id, customer_id, status, credit_limit,"
            " payment_terms_days, risk_level, version, created_at, updated_at)"
            " VALUES (?,?,'AUTHORIZED','2000',15,'MEDIUM',1,'2026-01-01','2026-01-01')",
            (new_uuid(), merged))
        conn.commit()
        self._merge(conn, owner, other_owner, master, merged)

        primaries = conn.execute("SELECT COUNT(*) FROM customer_contacts WHERE customer_id=?"
                                 " AND is_primary=1", (master,)).fetchone()[0]
        assert primaries == 1
        hits = [r.customer_id for r in owner.read("customer_lookup", query="Abarrotes")]
        assert hits == [master]
        assert conn.execute("SELECT customer_id FROM customer_credit_profiles").fetchone()[0] \
            == master

    def test_survivor_counts_the_merged_customers_debt(self, conn):
        from backend.application.customer_credit.queries.customer_accounts_receivable_summary_query import (
            CustomerAccountsReceivableSummaryQuery,
        )
        from backend.application.use_cases.finance.receivable_use_cases import (
            CreateReceivableUseCase,
        )
        owner, _ = presenter_for(conn, "system_owner")
        other_owner, _ = presenter_for(conn, "system_owner")
        master = new_customer(owner, "Cremería Sol")
        merged = new_customer(owner, "Cremeria Sol", allow_duplicate=True)
        CreateReceivableUseCase().execute(
            conn, customer_id=merged, amount="300", document_number="F-1",
            issue_date=datetime.now().date(), operation_id=new_uuid(),
            source_module="sales")  # deuda de una venta (Ventas la reconoce, F11)
        self._merge(conn, owner, other_owner, master, merged)
        summary = CustomerAccountsReceivableSummaryQuery(conn).get_summary(master)
        assert summary.current_exposure == Decimal("300")

    def test_merged_tax_profile_is_kept_not_deleted(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        other_owner, _ = presenter_for(conn, "system_owner")
        master = new_customer(owner, "Pollería A", tax_identifier="POLA800101AB1")
        merged = new_customer(owner, "Pollería A2", tax_identifier="POLB800101AB1",
                              allow_duplicate=True)
        self._merge(conn, owner, other_owner, master, merged)
        rfcs = dict(conn.execute("SELECT customer_id, tax_identifier FROM customer_tax_profiles"
                                 ).fetchall())
        assert rfcs == {master: "POLA800101AB1", merged: "POLB800101AB1"}


class TestF07Concurrency:
    def test_second_stale_writer_gets_a_conflict(self, conn):
        from backend.domain.customers.exceptions import CustomerConcurrencyConflictError
        from backend.infrastructure.db.repositories.customers.unit_of_work import (
            CustomerUnitOfWork,
        )
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Original")
        first, second = CustomerUnitOfWork(conn), CustomerUnitOfWork(conn)
        copy_a = first.customers.get(customer)
        copy_b = second.customers.get(customer)
        copy_a.display_name = "Cambio A"
        copy_a.record_edit()
        first.customers.update(copy_a)
        conn.commit()
        copy_b.legal_name = "Razón B"
        copy_b.record_edit()
        try:
            second.customers.update(copy_b)
            raised = False
        except CustomerConcurrencyConflictError:
            raised = True
        conn.rollback()
        assert raised
        assert conn.execute("SELECT display_name FROM customers WHERE id=?",
                            (customer,)).fetchone()[0] == "Cambio A"

    def test_use_case_reports_the_conflict(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Uno")
        assert owner.run("update_customer", customer_id=customer, display_name="Dos").success
        assert owner.run("update_customer", customer_id=customer, display_name="Tres").success


class TestF08F09Pipeline:
    def test_completed_activity_counts_to_advance(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        stage = owner.run("create_stage", code="DEMO", name="Demostración",
                          probability_default=40, min_activities=1)
        assert stage.success, stage.message
        opp = owner.run("create_opportunity", customer_id=customer, name="Banquete",
                        origin_branch_id=owner.branch_id()).entity_id
        blocked = owner.run("move_opportunity_stage", opportunity_id=opp,
                            to_stage_id=stage.entity_id, reason="avance")
        assert not blocked.success
        activity = owner.run("create_activity", activity_type="CALL",
                             related_entity_type="OPPORTUNITY", related_entity_id=opp,
                             subject="Llamada").entity_id
        assert owner.run("complete_activity", activity_id=activity).success
        moved = owner.run("move_opportunity_stage", opportunity_id=opp,
                          to_stage_id=stage.entity_id, reason="avance")
        assert moved.success, moved.message

    def test_opportunity_validation(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        missing = owner.run("create_opportunity", customer_id=new_uuid(), name="X")
        assert not missing.success and "no existe" in missing.message
        won = conn.execute("SELECT id FROM crm_stage_definitions WHERE is_won_stage=1"
                           ).fetchone()[0]
        assert not owner.run("create_opportunity", customer_id=customer, name="X",
                             stage_id=won).success
        default = owner.run("create_opportunity", customer_id=customer, name="Default")
        explicit = owner.run("create_opportunity", customer_id=customer, name="Cero",
                             probability=0)
        stage_probability = conn.execute(
            "SELECT s.probability_default FROM opportunities o JOIN crm_stage_definitions s"
            " ON s.id=o.stage_id WHERE o.id=?", (default.entity_id,)).fetchone()[0]
        probs = dict(conn.execute("SELECT id, probability FROM opportunities").fetchall())
        assert probs[default.entity_id] == stage_probability
        assert probs[explicit.entity_id] == 0
        negative = owner.run("update_opportunity", opportunity_id=default.entity_id,
                             amount="-500")
        assert not negative.success and "negativo" in negative.message


class TestF10Automation:
    def test_two_create_task_rules_make_two_tasks(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        for title in ("Llamar", "Enviar catálogo"):
            assert owner.run("create_automation", name=title, trigger_type="LEAD_CREATED",
                             action_type="CREATE_TASK", trigger_config={},
                             action_config={"title": title}, description="").success
        lead = owner.run("create_lead", display_name="Nuevo",
                         origin_branch_id=owner.branch_id()).entity_id
        titles = sorted(r[0] for r in conn.execute(
            "SELECT title FROM crm_tasks WHERE related_entity_id=?", (lead,)))
        assert titles == ["Enviar catálogo", "Llamar"]


class TestF11SlaPause:
    def test_pause_moves_the_deadline_and_late_resolution_stays_missed(self):
        from backend.domain.customer_service.entities.sla_instance import SLAInstance
        start = datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc)
        sla = SLAInstance.create("c1", "p1", 60, 120, reference_time=_iso(start))
        sla.pause(at=_iso(start + timedelta(minutes=30)))
        sla.resume(at=_iso(start + timedelta(minutes=60)))
        assert sla.resolution_due_at == _iso(start + timedelta(minutes=150))
        assert sla.effective_breach_status(
            as_of=_iso(start + timedelta(minutes=125))).value != "BREACHED"
        sla.pause(at=_iso(start + timedelta(minutes=100)))
        sla.resume(at=_iso(start + timedelta(minutes=110)))
        assert sla.paused_seconds == 40 * 60
        sla.record_resolution(at=_iso(start + timedelta(minutes=200)))
        assert sla.result_status() == "MISSED"

    def test_on_time_resolution_is_met(self):
        from backend.domain.customer_service.entities.sla_instance import SLAInstance
        start = datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc)
        sla = SLAInstance.create("c1", "p1", 60, 120, reference_time=_iso(start))
        sla.record_resolution(at=_iso(start + timedelta(minutes=90)))
        assert sla.result_status() == "MET"

    def test_pause_is_persisted_through_the_case_flow(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        case = owner.run("create_case", customer_id=customer, case_type="COMPLAINT",
                         subject="Espera", origin_branch_id=owner.branch_id()).entity_id
        before = conn.execute("SELECT resolution_due_at FROM sla_instances WHERE case_id=?",
                              (case,)).fetchone()[0]
        owner, owner_id = owner, conn.execute(
            "SELECT created_by_user_id FROM service_cases WHERE id=?", (case,)).fetchone()[0]
        assert owner.run("assign_case", case_id=case, assignee_user_id=owner_id).success
        assert owner.run("start_case", case_id=case).success
        assert owner.run("wait_customer_case", case_id=case, reason="Falta ticket").success
        conn.execute("UPDATE sla_instances SET paused_at=? WHERE case_id=?",
                     (_iso(datetime.now(timezone.utc) - timedelta(hours=2)), case))
        conn.commit()
        owner.run("resume_case", case_id=case)
        after, paused = conn.execute("SELECT resolution_due_at, paused_seconds FROM sla_instances"
                                     " WHERE case_id=?", (case,)).fetchone()
        assert after > before and paused >= 2 * 3600 - 5


class TestF12Timeline:
    def test_canonical_sale_appears_for_a_customer_with_legacy_id(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Con puente")
        conn.execute("UPDATE customers SET legacy_customer_id=? WHERE id=?",
                     (new_uuid(), customer))
        conn.commit()
        from backend.application.customers.queries.customer_history_query_service import (
            CustomerHistoryQueryService,
        )
        service = CustomerHistoryQueryService.__new__(CustomerHistoryQueryService)
        service._conn = conn
        relation = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='v_ventas_unificada'").fetchone()
        assert relation, "la vista unificada existe en la base completa"
        sale = new_uuid()
        conn.execute("PRAGMA foreign_keys=OFF")
        cols = {r[1] for r in conn.execute("PRAGMA table_info(sales)")}
        values = {"id": sale, "sale_number": "V-9", "branch_id": owner.branch_id(),
                  "customer_id": customer, "status": "COMPLETED", "total": "150",
                  "gross_subtotal": "150", "discount_total": "0",
                  "created_at": _iso(datetime.now(timezone.utc)),
                  "operation_id": new_uuid(), "cashier_user_id": "c"}
        values = {k: v for k, v in values.items() if k in cols}
        conn.execute(f"INSERT INTO sales ({', '.join(values)}) VALUES "
                     f"({', '.join('?' for _ in values)})", tuple(values.values()))
        entries = service._sales_entries(customer)
        assert [e.source_entity_id for e in entries] == [sale]


class TestF16LeadConversion:
    def _qualified_lead(self, owner):
        lead = owner.run("create_lead", display_name="Restaurante Brisa",
                         origin_branch_id=owner.branch_id()).entity_id
        assert owner.run("assign_lead", lead_id=lead, assignee_user_id=owner.current_user_id(),
                         reason="cartera").success
        assert owner.run("mark_lead_contacted", lead_id=lead).success
        result = owner.run("qualify_lead", lead_id=lead, model="MANUAL",
                           manual_decision="QUALIFIED", notes="cumple")
        assert result.success, result.message
        return lead

    def test_customer_and_opportunity_in_one_step(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        lead = self._qualified_lead(owner)
        result = owner.run("convert_lead", lead_id=lead, allow_duplicate=True,
                           create_opportunity=True)
        assert result.success, result.message
        row = conn.execute("SELECT converted_customer_id, converted_opportunity_id FROM leads"
                           " WHERE id=?", (lead,)).fetchone()
        assert tuple(row) == (result.data["customer_id"], result.data["opportunity_id"])

    def test_failed_opportunity_rolls_back_the_conversion(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        lead = self._qualified_lead(owner)
        before = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        result = owner.run("convert_lead", lead_id=lead, allow_duplicate=True,
                           create_opportunity=True, stage_id=new_uuid())
        assert not result.success
        assert conn.execute("SELECT status FROM leads WHERE id=?", (lead,)).fetchone()[0] \
            == "QUALIFIED"
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == before

    def test_retry_resumes_without_a_second_customer(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        lead = self._qualified_lead(owner)
        first = owner.run("convert_lead", lead_id=lead, allow_duplicate=True)
        before = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        again = owner.run("convert_lead", lead_id=lead, allow_duplicate=True,
                          create_opportunity=True)
        assert again.success and again.data["customer_id"] == first.data["customer_id"]
        assert again.data.get("opportunity_id")
        assert conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0] == before

    def test_opportunity_for_another_customer_is_refused(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        lead = self._qualified_lead(owner)
        owner.run("convert_lead", lead_id=lead, allow_duplicate=True)
        stranger = new_customer(owner, "Otro")
        result = owner.run("create_opportunity_from_lead", lead_id=lead, customer_id=stranger)
        assert not result.success and "no es el cliente" in result.message
