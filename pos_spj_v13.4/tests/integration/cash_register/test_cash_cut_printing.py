"""CASH-26 bloque 2 — los cortes se imprimen de verdad.

Medido 2026-10-07: el Corte X/Z se encolaba en HTML para la impresora literal
"default-cash-printer" y nada despachaba la cola; la pantalla decía «enviado a
impresión». Ahora la impresora la asigna Document Output (Corte X / Corte Z),
se renderiza ESC/POS y se entrega por la misma vía que el ticket de venta.
"""

from __future__ import annotations

import importlib
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from backend.application.security.permission_query_service import PermissionQueryService
from backend.bootstrap.application_context import ApplicationContext, FeatureContext
from backend.bootstrap.legacy_session_adapter import LegacySessionAdapter
from backend.domain.cash_register.exceptions import CashConfigurationError, CashInvalidStateError
from backend.infrastructure.db.repositories.security.permission_repository import (
    SqlitePermissionRepository,
)
from backend.infrastructure.desktop.cash_register_factory import build_cash_register_presenter
from backend.infrastructure.hardware.cash_document_printer import CashDocumentPrinter
from backend.infrastructure.printing.transport import PrintTransport
from backend.security.credentials.password_hasher import BcryptPasswordHasher
from backend.security.credentials.password_policy import PasswordPolicy
from backend.security.provisioning.installation_repository import SqliteInstallationRepository
from backend.security.provisioning.provision_installation_use_case import (
    ProvisionInstallationUseCase,
)
from backend.security.provisioning.recovery_code_repository import SqliteRecoveryCodeRepository
from backend.shared.events.application_bus import reset_bus
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
NOW = "2026-10-04T19:33:13+00:00"


class _Root:
    def __init__(self, conn, session, **extra):
        self.db, self.session = conn, session
        for key, value in extra.items():
            setattr(self, key, value)


class _Gateway:
    def __init__(self, error: Exception | None = None):
        self.jobs, self.error = [], error

    def print_job(self, job):
        if self.error:
            raise self.error
        self.jobs.append(job)
        return "PRN-01"


@pytest.fixture
def conn():
    reset_bus()
    c = make_db()
    ProvisionInstallationUseCase(
        c, installation_repository=SqliteInstallationRepository(c),
        recovery_code_repository=SqliteRecoveryCodeRepository(c),
        password_hasher=BcryptPasswordHasher(), password_policy=PasswordPolicy(),
    ).execute(company_name="SPJ", branch_name="Centro", owner_username="duena",
              workstation_name="Caja 1", owner_password="Correct-Horse-9!",
              owner_full_name="Duena", now=T0)
    for name in ("175_cash_register_bounded_context_schema",
                 "176_cash_register_configuration_schema",
                 "306_seed_cash_register_role_permissions",
                 "307_seed_cash_register_catalogs"):
        importlib.import_module(f"migrations.standalone.{name}").run(c)
    branch_id = _branch(c)
    register = new_uuid()
    c.execute("INSERT INTO cash_registers VALUES(?,?,?,?,?,?,?)",
              (register, branch_id, "CAJA-01", "ACTIVE", None, NOW, NOW))
    c.execute("INSERT INTO cash_drawers VALUES(?,?,?,?,?,?,?)",
              (new_uuid(), branch_id, register, "CAJON-01", "ACTIVE", NOW, NOW))
    c.execute("INSERT INTO pos_terminals VALUES(?,?,?,?,?,?,?)",
              (new_uuid(), branch_id, register, "TER-01", "ACTIVE", NOW, NOW))
    c.commit()
    yield c
    c.close()
    reset_bus()


def _branch(conn):
    return conn.execute("SELECT sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()[0]


def _ticket_printer(conn) -> str:
    """La instalación real: una térmica USB de 80 mm con ruta de ticket de venta."""
    profile, device = new_uuid(), new_uuid()
    conn.execute(
        "INSERT INTO device_profiles (id, name, device_type, manufacturer, model, connection_type,"
        " extra_parameters_json, capabilities_json, paper_profile, created_at, updated_at)"
        " VALUES (?, 'Impresion', 'THERMAL_PRINTER', 'Xprint', '', 'USB', '{}', '[]',"
        " 'PAPER_80MM', ?, ?)", (profile, NOW, NOW))
    conn.execute(
        "INSERT INTO devices (id, branch_id, profile_id, code, name, status, notes, created_at,"
        " updated_at) VALUES (?, ?, ?, 'PRN-01', 'TL2X Printer', 'ACTIVE', '', ?, ?)",
        (device, _branch(conn), profile, NOW, NOW))
    conn.execute(
        "INSERT INTO print_routes (id, document_type, primary_device_id, branch_id, module,"
        " active, created_at, updated_at) VALUES (?, 'SALE_TICKET', ?, ?, 'sales', 1, ?, ?)",
        (new_uuid(), device, _branch(conn), NOW, NOW))
    conn.commit()
    return device


def _run_309(conn):
    importlib.import_module("migrations.standalone.309_seed_cash_cut_print_routes").run(conn)


def _caja(conn, **extra):
    user_id, branch_id = conn.execute(
        "SELECT id, sucursal_id FROM usuarios WHERE usuario='duena'").fetchone()
    perms = PermissionQueryService(SqlitePermissionRepository(conn)).permission_codes_for_user(
        user_id, branch_id)
    ctx = ApplicationContext(
        installation_id="", company_id="", branch_id=branch_id, branch_name="Centro",
        assigned_branch_ids=frozenset({branch_id}), workstation_id="ws", workstation_type="",
        user_id=user_id, user_name="duena", roles=("system_owner",), permissions=frozenset(perms),
        feature_context=FeatureContext.from_flags_dict({}), session_id=new_uuid())
    return build_cash_register_presenter(_Root(conn, LegacySessionAdapter(ctx), **extra))


def _x_cut(caja):
    caja.open_cash_shift(opening_amount=Decimal("500.00"))
    return caja.generate_x_cut().entity_id


def test_309_routes_cuts_to_the_ticket_printer_once(conn):
    device = _ticket_printer(conn)
    _run_309(conn)
    _run_309(conn)
    rows = conn.execute("SELECT document_type, primary_device_id, module FROM print_routes"
                        " WHERE document_type IN ('X_REPORT','Z_REPORT') ORDER BY 1").fetchall()
    assert [tuple(r) for r in rows] == [("X_REPORT", device, None), ("Z_REPORT", device, None)]


def test_309_respects_a_cut_route_already_assigned(conn):
    _ticket_printer(conn)
    other = conn.execute("SELECT primary_device_id FROM print_routes").fetchone()[0]
    conn.execute("INSERT INTO print_routes (id, document_type, primary_device_id, branch_id,"
                 " active, created_at, updated_at) VALUES (?, 'Z_REPORT', ?, ?, 0, ?, ?)",
                 (new_uuid(), other, _branch(conn), NOW, NOW))
    _run_309(conn)
    assert conn.execute("SELECT COUNT(*) FROM print_routes WHERE document_type='Z_REPORT'"
                        ).fetchone()[0] == 1


def test_without_a_cut_route_printing_explains_where_to_assign_it(conn):
    caja = _caja(conn, cash_print_gateway=_Gateway())
    cut_id = _x_cut(caja)
    with pytest.raises(CashConfigurationError, match="Corte X"):
        caja.print_x_cut(cut_id=cut_id)
    assert conn.execute("SELECT COUNT(*) FROM cash_print_jobs").fetchone()[0] == 0


def test_x_cut_prints_escpos_on_the_routed_printer(conn):
    device = _ticket_printer(conn)
    _run_309(conn)
    gateway = _Gateway()
    caja = _caja(conn, cash_print_gateway=gateway)
    cut_id = _x_cut(caja)
    print_id = caja.print_x_cut(cut_id=cut_id)
    assert len(gateway.jobs) == 1
    job = gateway.jobs[0]
    assert job.printer_id == device and job.media_type == "application/vnd.escpos"
    assert job.content.startswith(b"\x1b@") and b"CORTE X" in job.content.upper()
    assert conn.execute("SELECT status FROM cash_print_jobs WHERE id=?",
                        (print_id,)).fetchone()[0] == "PRINTED"


def test_a_printer_that_fails_is_reported_and_can_be_reprinted(conn):
    _ticket_printer(conn)
    _run_309(conn)
    caja = _caja(conn, cash_print_gateway=_Gateway(RuntimeError("sin papel")))
    cut_id = _x_cut(caja)
    with pytest.raises(CashInvalidStateError, match="no se imprimió: sin papel"):
        caja.print_x_cut(cut_id=cut_id)
    assert conn.execute("SELECT status FROM cash_print_jobs").fetchone()[0] == "FAILED"
    ok = _caja(conn, cash_print_gateway=_Gateway())
    ok.print_x_cut(cut_id=cut_id, reprint=True, reprint_reason="Sin papel en la primera")
    assert conn.execute("SELECT COUNT(*) FROM cash_print_jobs WHERE status='PRINTED'"
                        ).fetchone()[0] == 1


def test_real_gateway_sends_each_copy_through_the_ticket_transport(conn, monkeypatch):
    device = _ticket_printer(conn)
    sent = []
    monkeypatch.setattr(PrintTransport, "send",
                        staticmethod(lambda data, *a, **k: sent.append(data) or True))
    from backend.application.cash_register.printing import CashQueuedPrintJob

    job = CashQueuedPrintJob(print_id=new_uuid(), printer_id=device, content=b"\x1b@corte",
                             media_type="application/vnd.escpos", filename="x.bin", copies=2)
    assert CashDocumentPrinter(conn).print_job(job) == "PRN-01"
    assert sent == [b"\x1b@corte", b"\x1b@corte"]
    monkeypatch.setattr(PrintTransport, "send", staticmethod(lambda *a, **k: False))
    with pytest.raises(Exception, match="apagada o sin papel"):
        CashDocumentPrinter(conn).print_job(job)
