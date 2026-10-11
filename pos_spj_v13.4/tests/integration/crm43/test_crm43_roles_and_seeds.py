"""CRM-43 — matriz de roles (migr. 314), SLA sembrado (315) y proyección de
compras recuperada (316), sobre la base con todas las migraciones.

Medido en la base real el 2026-10-08: sólo el dueño entraba al módulo;
gerente, cajero y solo_lectura veían «No tienes permiso», y el cajero no podía
buscar clientes en el POS (``CLIENTES.buscar``).
"""

from __future__ import annotations

import importlib
import json

import pytest

from backend.application.crm.permissions import ALL_CRM_PERMISSIONS, CRMPermissions
from backend.application.customers.permissions import (
    ALL_CUSTOMER_PERMISSIONS,
    CustomerPermissions,
)
from backend.shared.ids import new_uuid
from tests.integration.crm43.conftest import add_user, branch_id, presenter_for, session_for

_314 = importlib.import_module("migrations.standalone.314_seed_customers_crm_role_permissions")
_315 = importlib.import_module("migrations.standalone.315_seed_service_level_policies")
_316 = importlib.import_module("migrations.standalone.316_backfill_customer_sales_projection")


def _can(conn, role: str, code: str) -> bool:
    uid = add_user(conn, role)
    return session_for(conn, uid, role).tiene_permiso(code)


class TestRoleMatrix:
    def test_snapshot_covers_the_whole_live_catalog(self):
        clientes = {code.split(".", 1)[1] for code in ALL_CUSTOMER_PERMISSIONS}
        crm = {code.split(".", 1)[1] for code in ALL_CRM_PERMISSIONS}
        assert set(_314._CLIENTES) == clientes
        assert set(_314._CRM) == crm

    @pytest.mark.parametrize("role", ["gerente", "cajero", "solo_lectura"])
    def test_every_crm_role_enters_the_module_and_the_menu(self, conn, role):
        assert _can(conn, role, CustomerPermissions.ACCESS)
        assert _can(conn, role, "CLIENTES_CRM.ver")

    @pytest.mark.parametrize("role", ["almacen", "repartidor"])
    def test_warehouse_and_driver_have_no_access(self, conn, role):
        assert not _can(conn, role, CustomerPermissions.ACCESS)

    def test_cashier_can_search_and_register_but_not_approve_credit(self, conn):
        for code in (CustomerPermissions.SEARCH, CustomerPermissions.CREATE,
                     CustomerPermissions.CONSENT_CAPTURE, CRMPermissions.CASES_CREATE,
                     CustomerPermissions.COMMERCIAL_ELIGIBILITY_CHECK):
            assert _can(conn, "cajero", code), code
        for code in (CustomerPermissions.CREDIT_APPROVE, CustomerPermissions.CREDIT_VIEW,
                     CRMPermissions.LEADS_VIEW, CustomerPermissions.SENSITIVE_DATA_VIEW):
            assert not _can(conn, "cajero", code), code

    def test_manager_supervises_branch_and_approves_credit_but_not_configuration(self, conn):
        for code in (CRMPermissions.LEADS_VIEW_BRANCH, CRMPermissions.CASES_VIEW_BRANCH,
                     CustomerPermissions.CREDIT_APPROVE, CRMPermissions.OPPORTUNITIES_REASSIGN):
            assert _can(conn, "gerente", code), code
        for code in (CRMPermissions.PIPELINE_CONFIGURE, CRMPermissions.SLA_MANAGE,
                     CustomerPermissions.ANONYMIZE, CustomerPermissions.SENSITIVE_DATA_EXPORT):
            assert not _can(conn, "gerente", code), code

    def test_read_only_cannot_mutate(self, conn):
        assert _can(conn, "solo_lectura", CustomerPermissions.VIEW)
        for code in (CustomerPermissions.CREATE, CustomerPermissions.EDIT,
                     CRMPermissions.CASES_CREATE, CRMPermissions.LEADS_CREATE):
            assert not _can(conn, "solo_lectura", code), code

    def test_legacy_delete_code_is_removed_and_rerun_is_idempotent(self, conn):
        assert conn.execute("SELECT COUNT(*) FROM rol_permisos WHERE upper(modulo)='CLIENTES'"
                            " AND lower(accion)='eliminar'").fetchone()[0] == 0
        before = conn.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0]
        _314.run(conn)
        assert conn.execute("SELECT COUNT(*) FROM rol_permisos").fetchone()[0] == before

    def test_cashier_finds_customers_from_the_pos(self, conn):
        """El POS busca con ``CLIENTES.buscar``; antes el cajero no lo tenía."""
        from backend.application.customers.authorization import CustomerAuthorizationPolicy
        from backend.application.customers.session_authorization import (
            CustomerSessionPermissionChecker,
        )
        from backend.infrastructure.integrations.sales_customer_client import (
            SalesCustomerClient,
        )
        owner, _ = presenter_for(conn, "system_owner")
        owner.run("create_customer", display_name="Taquería El Güero")
        uid = add_user(conn, "cajero")
        session = session_for(conn, uid, "cajero")
        client = SalesCustomerClient(conn, authorization=CustomerAuthorizationPolicy(
            CustomerSessionPermissionChecker(session)))
        assert [r.display_name for r in client.search("Güero", actor_user_id=uid)] == [
            "Taquería El Güero"]


class TestServiceLevelSeed:
    def test_five_priorities_seeded_with_the_users_times(self, conn):
        rows = {r["priority"]: (r["first_response_minutes"], r["resolution_minutes"])
                for r in conn.execute("SELECT * FROM service_level_policies WHERE active=1")}
        assert rows == {"LOW": (480, 4320), "NORMAL": (240, 2880), "HIGH": (60, 1440),
                        "URGENT": (30, 480), "CRITICAL": (30, 480)}

    def test_rerun_never_duplicates_nor_overrides(self, conn):
        conn.execute("UPDATE service_level_policies SET resolution_minutes=999 WHERE code='SLA-ALTA'")
        _315.run(conn)
        assert conn.execute("SELECT COUNT(*) FROM service_level_policies").fetchone()[0] == 5
        assert conn.execute("SELECT resolution_minutes FROM service_level_policies"
                            " WHERE code='SLA-ALTA'").fetchone()[0] == 999

    def test_a_new_case_gets_its_sla(self, conn):
        presenter, _ = presenter_for(conn, "gerente")
        customer = presenter.run("create_customer", display_name="Cliente").entity_id
        case = presenter.run("create_case", customer_id=customer, case_type="COMPLAINT",
                             subject="Llegó caliente", priority="HIGH")
        assert case.success
        assert conn.execute("SELECT COUNT(*) FROM sla_instances WHERE case_id=?",
                            (case.entity_id,)).fetchone()[0] == 1


class TestSalesProjectionBackfill:
    def _outbox(self, conn, event_name: str, customer_id: str, event_id: str) -> None:
        payload = {"event_id": event_id, "event_name": event_name, "entity_id": new_uuid(),
                   "timestamp": "2026-10-08T03:04:54+00:00",
                   "payload": {"customer_id": customer_id}}
        conn.execute("INSERT INTO sales_outbox (id, event_id, event_name, payload_json,"
                     " operation_id, status, created_at) VALUES (?,?,?,?,?,?,datetime('now'))",
                     (new_uuid(), event_id, event_name, json.dumps(payload), new_uuid(),
                      "DISPATCHED"))
        conn.commit()

    def test_already_dispatched_sales_are_counted_once(self, conn):
        presenter, _ = presenter_for(conn, "system_owner")
        customer = presenter.run("create_customer", display_name="Cliente").entity_id
        self._outbox(conn, "SALE_COMPLETED", customer, new_uuid())
        self._outbox(conn, "SALE_COMPLETED", customer, new_uuid())
        self._outbox(conn, "SALE_REVERSED", customer, new_uuid())
        _316.run(conn)
        _316.run(conn)
        count, last = conn.execute("SELECT purchase_count, last_purchase_at FROM customers"
                                   " WHERE id=?", (customer,)).fetchone()
        assert count == 1
        assert last == "2026-10-08T03:04:54+00:00"

    def test_branch_of_template_exists(self, conn):
        assert branch_id(conn)
