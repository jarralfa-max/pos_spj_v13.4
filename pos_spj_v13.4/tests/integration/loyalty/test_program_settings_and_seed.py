"""Fidelidad → Ajustes y la siembra de la migración 289 (2026-10-02).

* La página carga las reglas vigentes y guarda lo que se capture, en %, como
  fracción para el caso de uso; sin permiso queda en sólo lectura.
* La migración 289 siembra lo que el usuario decidió (canje para cajero,
  gerente y admin; reembolso para gerente y admin; tope de $5,000; 1 punto por
  cada $10, crédito acumula, 12 meses) y es idempotente.
"""

from __future__ import annotations

import importlib
import os
import sqlite3
from decimal import Decimal

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from backend.application.loyalty.queries.program_settings_query import (  # noqa: E402
    LoyaltyProgramSettingsQuery,
)
from backend.infrastructure.db.schema.loyalty_schema import create_loyalty_schema  # noqa: E402
from backend.shared.ids import new_uuid  # noqa: E402

_289 = importlib.import_module("migrations.standalone.289_sales_returns_loyalty_seed")
_176 = importlib.import_module("migrations.standalone.176_cash_register_configuration_schema")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_loyalty_schema(c)
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT,"
              " tipo TEXT, grupo TEXT, descripcion TEXT)")
    c.commit()
    yield c
    c.close()


# ── página ───────────────────────────────────────────────────────────────────

class _Session:
    def __init__(self, permisos):
        self.user_id = new_uuid()
        self.active_branch_id = new_uuid()
        self.is_active = True
        self._permisos = permisos

    def tiene_permiso(self, code):
        return code in self._permisos


@pytest.fixture(scope="module")
def app():
    pytest.importorskip("PyQt5")
    from PyQt5.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


def _page(conn, permisos):
    from frontend.desktop.modules.fidelidad.composition import build_fidelidad_presenter
    from frontend.desktop.modules.fidelidad.pages.program_settings_page import (
        ProgramSettingsPage,
    )

    return ProgramSettingsPage(build_fidelidad_presenter(conn, _Session(permisos)))


def test_the_page_loads_the_current_rules_and_saves_them(app, conn):
    page = _page(conn, {"GROWTH_ENGINE.configuracion.ver", "GROWTH_ENGINE.configuracion.editar"})
    assert page.pesos_per_point.decimal_value() == Decimal("10")
    assert page.expiration_months.value() == 12
    assert page.max_percent.decimal_value() == Decimal("50")

    page.pesos_per_point.set_decimal("20")
    page.expiration_months.setValue(0)
    page.max_percent.set_decimal_value(Decimal("30"))
    page.credit_earns.setChecked(False)
    page.save()

    settings = LoyaltyProgramSettingsQuery(conn).current()
    assert settings.accrual.pesos_per_point == Decimal("20")
    assert settings.accrual.expiration_months == 0
    assert settings.accrual.credit_earns is False
    assert settings.redemption.max_percent == Decimal("0.3")
    assert "guardados" in page._status.text()


def test_without_the_permission_the_page_is_read_only(app, conn):
    page = _page(conn, {"GROWTH_ENGINE.configuracion.ver"})
    assert not page.btn_save.isEnabled()
    assert not page.pesos_per_point.isEnabled()
    assert "Sólo lectura" in page._status.text()


# ── migración 289 ────────────────────────────────────────────────────────────

def _seed_base(conn, *, owner_id):
    conn.execute("CREATE TABLE roles (id TEXT PRIMARY KEY, nombre TEXT)")
    conn.execute("CREATE TABLE rol_permisos (id TEXT PRIMARY KEY, rol_id TEXT, modulo TEXT,"
                 " accion TEXT, permitido INTEGER DEFAULT 1, UNIQUE(rol_id, modulo, accion))")
    conn.execute("CREATE TABLE usuarios (id TEXT PRIMARY KEY, rol TEXT)")
    for rol in ("cajero", "gerente", "admin", "system_owner"):
        conn.execute("INSERT INTO roles VALUES (?, ?)", (new_uuid(), rol))
    conn.execute("INSERT INTO usuarios VALUES (?, 'system_owner')", (owner_id,))
    _176.run(conn)
    conn.commit()


def _granted(conn, rol):
    return {f"{r[0]}.{r[1]}" for r in conn.execute(
        "SELECT rp.modulo, rp.accion FROM rol_permisos rp JOIN roles r ON r.id = rp.rol_id"
        " WHERE r.nombre = ?", (rol,))}


def test_migration_289_seeds_the_user_decisions_once(conn):
    _seed_base(conn, owner_id=new_uuid())
    _289.run(conn)
    _289.run(conn)

    assert _granted(conn, "cajero") == {"GROWTH_ENGINE.puntos.canjear"}
    assert "CAJA.reembolso.autorizar" in _granted(conn, "gerente")
    assert "GROWTH_ENGINE.configuracion.editar" not in _granted(conn, "gerente")
    assert "GROWTH_ENGINE.configuracion.editar" in _granted(conn, "admin")
    [tope] = conn.execute("SELECT approval_threshold, hard_cap FROM cash_operation_limits"
                          " WHERE operation_type='REFUND'").fetchall()
    assert tuple(tope) == ("5000", "5000")
    accrual = LoyaltyProgramSettingsQuery(conn).accrual()
    assert (accrual.pesos_per_point, accrual.credit_earns, accrual.expiration_months) == (
        Decimal("10"), True, 12)


def test_migration_289_never_overwrites_an_existing_refund_cap_or_rule(conn):
    owner = new_uuid()
    _seed_base(conn, owner_id=owner)
    conn.execute("INSERT INTO cash_operation_limits (id, operation_type, approval_threshold,"
                 " hard_cap, scope_type, scope_id, effective_from, effective_to, created_by)"
                 " VALUES (?, 'REFUND', '1000', '2000', 'SYSTEM', NULL, '2026-01-01', NULL, ?)",
                 (new_uuid(), owner))
    conn.execute("INSERT INTO configuraciones (clave, valor) VALUES"
                 " ('loyalty_pesos_por_punto', '25')")
    _289.run(conn)

    assert [tuple(r) for r in conn.execute(
        "SELECT approval_threshold, hard_cap FROM cash_operation_limits")] == [("1000", "2000")]
    assert LoyaltyProgramSettingsQuery(conn).accrual().pesos_per_point == Decimal("25")
