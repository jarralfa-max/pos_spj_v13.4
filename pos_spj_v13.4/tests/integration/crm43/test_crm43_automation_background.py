"""CRM-43 (cierre de pendientes) — ciclo de fondo, avisos y alcance por registro.

Con la base completa (todas las migraciones) y el presentador REAL:

* las siete reglas por tiempo de §56 se disparan una vez por registro y ancla;
* «Enviar aviso» y los recordatorios llegan a la bandeja que lee la campana;
* «Cambiar prioridad» cambia prospectos y casos;
* una regla que no puede ejecutarse no se guarda;
* el alcance (propios / sucursal / empresa) también protege las acciones, no
  sólo las bandejas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.application.crm.background_cycle import run_crm_background_cycle
from backend.application.notifications.user_inbox_service import UserInboxService
from tests.integration.crm43.conftest import add_branch, add_user, new_customer, presenter_for


def _ago(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="seconds")


def _rule(presenter, trigger, action, *, trigger_config=None, action_config=None, name=None):
    result = presenter.run("create_automation", name=name or f"{trigger} → {action}",
                           trigger_type=trigger, action_type=action,
                           trigger_config=trigger_config or {},
                           action_config=action_config or {}, description="")
    assert result.success, result.message
    return result.entity_id


def _inbox(conn, user_id):
    return UserInboxService(conn).recent(user_id)


def _executions(conn, rule_id):
    return conn.execute("SELECT target_entity_id, status, result_detail"
                        " FROM crm_automation_executions WHERE rule_id=?", (rule_id,)).fetchall()


class TestRuleValidation:
    def test_incompatible_action_is_rejected_with_a_reason(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        result = owner.run("create_automation", name="Mal", trigger_type="CUSTOMER_INACTIVE",
                           action_type="ESCALATE_CASE", trigger_config={"days": 30},
                           action_config={"escalated_to_user_id": "x"}, description="")
        assert not result.success
        assert "no aplica a clientes" in result.message

    def test_threshold_trigger_needs_days(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        result = owner.run("create_automation", name="Sin días", trigger_type="LEAD_IDLE",
                           action_type="CREATE_TASK", trigger_config={}, action_config={},
                           description="")
        assert not result.success
        assert "cuántos días" in result.message

    def test_notification_needs_a_recipient(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        result = owner.run("create_automation", name="Aviso", trigger_type="LEAD_CREATED",
                           action_type="SEND_NOTIFICATION", trigger_config={},
                           action_config={}, description="")
        assert not result.success
        assert "quién recibe" in result.message


class TestTimeBasedTriggers:
    def test_idle_lead_notifies_its_responsible_once(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        seller = add_user(conn, "gerente", name="Vendedora")
        lead = owner.run("create_lead", display_name="Taquería Lupita",
                         origin_branch_id=owner.branch_id()).entity_id
        assert owner.run("assign_lead", lead_id=lead, assignee_user_id=seller,
                         reason="cartera").success
        rule = _rule(owner, "LEAD_IDLE", "SEND_NOTIFICATION", trigger_config={"days": 3},
                     action_config={"notify_responsible": True, "message": "Llámale hoy"})
        conn.execute("UPDATE leads SET updated_at=?, created_at=? WHERE id=?",
                     (_ago(10), _ago(10), lead))
        conn.commit()

        first = run_crm_background_cycle(conn)
        second = run_crm_background_cycle(conn)

        assert first.automation_executions == 1 and second.automation_executions == 0
        avisos = _inbox(conn, seller)
        assert len(avisos) == 1
        assert avisos[0].title == "LEAD_IDLE → SEND_NOTIFICATION"
        assert "Taquería Lupita" in avisos[0].body and "Llámale hoy" in avisos[0].body
        assert [r["status"] for r in _executions(conn, rule)] == ["SUCCEEDED"]

    def test_lead_becomes_eligible_again_after_it_moves(self, conn):
        owner, owner_id = presenter_for(conn, "system_owner")
        lead = owner.run("create_lead", display_name="Fonda",
                         origin_branch_id=owner.branch_id()).entity_id
        _rule(owner, "LEAD_IDLE", "SEND_NOTIFICATION", trigger_config={"days": 3},
              action_config={"recipient_user_id": owner_id})
        conn.execute("UPDATE leads SET updated_at=?, created_at=? WHERE id=?",
                     (_ago(10), _ago(10), lead))
        conn.commit()
        run_crm_background_cycle(conn)
        # se movió hace 5 días (después del primer aviso no, pero el ancla cambió)
        conn.execute("UPDATE leads SET updated_at=? WHERE id=?", (_ago(5), lead))
        conn.execute("UPDATE crm_automation_executions SET executed_at=?", (_ago(9),))
        conn.commit()
        run_crm_background_cycle(conn)
        assert len(_inbox(conn, owner_id)) == 2

    def test_inactive_customer_gets_a_task(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner, "Cliente dormido")
        conn.execute("UPDATE customers SET last_purchase_at=? WHERE id=?", (_ago(120), customer))
        new_customer(owner, "Nunca compró")
        conn.commit()
        rule = _rule(owner, "CUSTOMER_INACTIVE", "CREATE_TASK", trigger_config={"days": 90},
                     action_config={"title": "Reactivar cliente", "due_in_hours": 48})

        run_crm_background_cycle(conn)

        executions = _executions(conn, rule)
        assert [(r["target_entity_id"], r["status"]) for r in executions] == [
            (customer, "SUCCEEDED")]
        task = conn.execute("SELECT related_entity_type, related_entity_id, title FROM crm_tasks"
                            " WHERE related_entity_id=?", (customer,)).fetchone()
        assert tuple(task) == ("CUSTOMER", customer, "Reactivar cliente")

    def test_overdue_opportunity_notifies_a_fixed_person(self, conn):
        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        opp = owner.run("create_opportunity", customer_id=customer, name="Banquete",
                        origin_branch_id=owner.branch_id()).entity_id
        conn.execute("UPDATE opportunities SET expected_close_date=? WHERE id=?",
                     ((datetime.now() - timedelta(days=2)).date().isoformat(), opp))
        conn.commit()
        _rule(owner, "OPPORTUNITY_OVERDUE", "SEND_NOTIFICATION",
              action_config={"recipient_user_id": owner_id})

        run_crm_background_cycle(conn)

        assert ["Oportunidad: Banquete"] == [a.body for a in _inbox(conn, owner_id)]

    def test_breached_sla_raises_case_priority(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        case = owner.run("create_case", customer_id=customer, case_type="COMPLAINT",
                         subject="Pedido incompleto", priority="NORMAL",
                         origin_branch_id=owner.branch_id()).entity_id
        conn.execute("UPDATE sla_instances SET first_response_due_at=?, resolution_due_at=?"
                     " WHERE case_id=?", (_ago(2), _ago(1), case))
        conn.commit()
        _rule(owner, "SLA_BREACHED", "CHANGE_PRIORITY", action_config={"priority": "CRITICAL"})

        run_crm_background_cycle(conn)

        assert conn.execute("SELECT priority FROM service_cases WHERE id=?",
                            (case,)).fetchone()[0] == "CRITICAL"

    def test_credit_review_due_tags_the_customer(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        tag = owner.run("create_tag", code="REVISAR", label="Revisar crédito").entity_id
        assert owner.run("request_credit", customer_id=customer, requested_limit=5000,
                         payment_terms_days=15).success
        conn.execute("UPDATE customer_credit_profiles SET status='AUTHORIZED', authorized_at=?,"
                     " review_at=NULL WHERE customer_id=?", (_ago(400), customer))
        conn.commit()
        _rule(owner, "CREDIT_REVIEW_DUE", "ADD_TAG", trigger_config={"days": 365},
              action_config={"tag_id": tag})

        run_crm_background_cycle(conn)

        assert conn.execute("SELECT COUNT(*) FROM customer_tag_assignments"
                            " WHERE customer_id=? AND tag_id=?", (customer, tag)).fetchone()[0] == 1

    def test_idle_lead_priority_change(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        lead = owner.run("create_lead", display_name="Cafetería",
                         origin_branch_id=owner.branch_id()).entity_id
        _rule(owner, "LEAD_IDLE", "CHANGE_PRIORITY", trigger_config={"days": 7},
              action_config={"priority": "HIGH"})
        conn.execute("UPDATE leads SET updated_at=?, created_at=? WHERE id=?",
                     (_ago(8), _ago(8), lead))
        conn.commit()

        run_crm_background_cycle(conn)

        assert conn.execute("SELECT priority FROM leads WHERE id=?", (lead,)).fetchone()[0] == "HIGH"


class TestReminders:
    def test_due_reminder_reaches_the_inbox_once(self, conn):
        owner, owner_id = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        task = owner.run("create_task", related_entity_type="CUSTOMER",
                         related_entity_id=customer, title="Cobrar factura",
                         due_at=_ago(-1)).entity_id
        assert owner.run("create_reminder", channel="IN_APP", remind_at=_ago(0.01),
                         recipient_user_id=owner_id, message="Hoy vence", task_id=task).success
        assert owner.run("create_reminder", channel="IN_APP", remind_at=_ago(-1),
                         recipient_user_id=owner_id, message="Mañana", task_id=task).success

        assert run_crm_background_cycle(conn).reminders_delivered == 1
        assert run_crm_background_cycle(conn).reminders_delivered == 0

        avisos = _inbox(conn, owner_id)
        assert [(a.title, a.body) for a in avisos] == [
            ("Recordatorio", "Hoy vence\nTarea: Cobrar factura")]

    def test_only_the_recipient_can_mark_it_read(self, conn):
        owner, owner_id = presenter_for(conn, "system_owner")
        intruder = add_user(conn, "cajero")
        customer = new_customer(owner)
        task = owner.run("create_task", related_entity_type="CUSTOMER",
                         related_entity_id=customer, title="Llamar", due_at=_ago(-1)).entity_id
        owner.run("create_reminder", channel="IN_APP", remind_at=_ago(0.01),
                  recipient_user_id=owner_id, message="", task_id=task)
        run_crm_background_cycle(conn)
        inbox = UserInboxService(conn)
        aviso = inbox.recent(owner_id)[0]

        assert inbox.mark_read(intruder, aviso.id) is False
        assert inbox.unread_count(owner_id) == 1
        assert inbox.mark_read(owner_id, aviso.id) is True
        assert inbox.unread_count(owner_id) == 0


class TestRecordScope:
    def _case(self, presenter, customer, subject):
        result = presenter.run("create_case", customer_id=customer, case_type="COMPLAINT",
                               subject=subject, origin_branch_id=presenter.branch_id())
        assert result.success, result.message
        return result.entity_id

    def test_cashier_cannot_operate_another_cashiers_case(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        cashier, _ = presenter_for(conn, "cajero")
        other, _ = presenter_for(conn, "cajero")
        theirs = self._case(other, customer, "De otro")
        mine = self._case(cashier, customer, "Mío")

        denied = cashier.run("update_case", case_id=theirs, subject="Cambiado")
        note = cashier.run("create_note", related_entity_type="CASE", related_entity_id=theirs,
                           body="metiche")

        assert not denied.success and denied.error_code == "OUT_OF_SCOPE"
        assert "fuera de tu alcance" in denied.message
        assert not note.success and note.error_code == "OUT_OF_SCOPE"
        assert conn.execute("SELECT subject FROM service_cases WHERE id=?",
                            (theirs,)).fetchone()[0] == "De otro"
        assert cashier.run("update_case", case_id=mine, subject="Mío editado").success

    def test_manager_operates_branch_cases_but_not_other_branches(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        cashier, _ = presenter_for(conn, "cajero")
        case = self._case(cashier, customer, "Del centro")
        manager, _ = presenter_for(conn, "gerente")
        north = add_branch(conn, "Norte")
        manager_north, _ = presenter_for(conn, "gerente", branch=north)

        assert manager.run("update_case", case_id=case, subject="Revisado").success
        denied = manager_north.run("update_case", case_id=case, subject="Ajeno")
        assert denied.error_code == "OUT_OF_SCOPE"

    def test_owner_has_company_scope(self, conn):
        owner, _ = presenter_for(conn, "system_owner")
        customer = new_customer(owner)
        north = add_branch(conn, "Norte")
        manager_north, _ = presenter_for(conn, "gerente", branch=north)
        case = self._case(manager_north, customer, "Del norte")
        assert owner.run("update_case", case_id=case, subject="Visto por dueño").success

    def test_missing_record_is_reported_by_the_use_case(self, conn):
        cashier, _ = presenter_for(conn, "cajero")
        result = cashier.run("update_case", case_id="no-existe", subject="x")
        assert result.error_code == "NOT_FOUND"
