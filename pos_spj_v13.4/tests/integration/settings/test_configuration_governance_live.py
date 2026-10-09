"""Gobierno de configuración en servicio (SET-26).

Antes: dominio y repositorios completos, 0 casos de uso, 0 consumidores y
`configuration_values` vacía; cada contexto leía texto suelto de
`configuraciones`. Estas pruebas recorren lo que ahora usan los contextos.

Configuración NO tiene pantalla para estos parámetros: cada uno se edita en su
módulo (decisión del usuario, 2026-10-04). La última prueba lo fija.
"""

from __future__ import annotations

import importlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from backend.application.settings import catalog as catalog_module
from backend.application.settings.catalog import SETTINGS_CATALOG, SettingSpec
from backend.application.settings.configuration_reader import ConfigurationReader
from backend.application.settings.governance import GovernedSettingsWriter
from backend.application.procurement.queries.tolerance_settings_query_service import (
    ProcurementToleranceSettingsQueryService,
)
from backend.domain.settings.enums import ConfigurationValueStatus, ScopeType, ValueType
from backend.domain.settings.events import ConfigurationEvents
from backend.domain.settings.exceptions import (
    ConfigurationApprovalRequiredError,
    ConfigurationInvalidValueError,
    ConfigurationScopeNotAllowedError,
)
from backend.infrastructure.db.repositories.settings.configuration_value_repository import (
    SqliteConfigurationValueRepository,
)
from backend.shared.events.application_bus import get_bus
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db
from tests.integration._governed_settings import ensure_governance, set_setting

APP = Path(__file__).resolve().parents[3]
TOL = "meat_processing.yield.tolerance_pct"
CRITICAL = "test_governance.critical_flag"

@pytest.fixture
def conn():
    connection = make_db()
    ensure_governance(connection)
    yield connection
    connection.close()


@pytest.fixture
def critical(conn, monkeypatch):
    """Un parámetro crítico de prueba: el catálogo real todavía no tiene ninguno."""
    spec = SettingSpec(CRITICAL, "test_governance", "Pruebas", "Bandera crítica",
                       ValueType.BOOLEAN, False, approval_required=True)
    monkeypatch.setitem(catalog_module.CATALOG_BY_KEY, CRITICAL, spec)
    monkeypatch.setattr(catalog_module, "SETTINGS_CATALOG", SETTINGS_CATALOG + (spec,))
    catalog_module.sync_configuration_catalog(conn)
    conn.commit()
    return CRITICAL


# ── lectura ─────────────────────────────────────────────────────────────────
def test_without_a_saved_value_the_catalog_default_rules_and_says_so(conn):
    efectiva = ConfigurationReader(conn).resolve(TOL)
    assert efectiva.value == Decimal("5") and efectiva.is_default


def test_a_change_is_a_new_version_and_expires_the_previous(conn):
    set_setting(conn, TOL, "6")
    set_setting(conn, TOL, "7")
    efectiva = ConfigurationReader(conn).resolve(TOL)
    assert (efectiva.value, efectiva.version, efectiva.source_scope_type) == (
        Decimal("7"), 2, "GLOBAL")
    lineage = [v.status for v in SqliteConfigurationValueRepository(conn).list_for_definition(
        efectiva and _definition_id(conn, TOL))]
    assert lineage == [ConfigurationValueStatus.ACTIVE, ConfigurationValueStatus.EXPIRED]


def test_inheritance_most_specific_scope_wins(conn):
    branch, other, species = new_uuid(), new_uuid(), new_uuid()
    set_setting(conn, TOL, "6")
    set_setting(conn, TOL, "8", scope_type=ScopeType.BRANCH, scope_id=branch)
    set_setting(conn, TOL, "12", scope_type=ScopeType.SPECIES, scope_id=species)
    reader = ConfigurationReader(conn)
    assert reader.get(TOL, context={ScopeType.BRANCH: other}) == Decimal("6")
    assert reader.get(TOL, context={ScopeType.BRANCH: branch}) == Decimal("8")
    assert reader.resolve(TOL, context={ScopeType.BRANCH: branch, ScopeType.SPECIES: species}
                          ).source_scope_type == "SPECIES"


def test_a_scope_the_definition_does_not_allow_is_rejected(conn):
    with pytest.raises(ConfigurationScopeNotAllowedError):
        set_setting(conn, "loyalty.pesos_per_point", "5", scope_type=ScopeType.BRANCH,
                    scope_id=new_uuid())


def test_invalid_values_never_get_stored(conn):
    with pytest.raises(ConfigurationInvalidValueError):
        set_setting(conn, "loyalty.points_expiration_months", "500")  # máximo 120
    with pytest.raises(ConfigurationInvalidValueError):
        set_setting(conn, "costing.cost_policy", "FIFO")
    assert conn.execute("SELECT COUNT(*) FROM configuration_values").fetchone()[0] == 0


def test_procurement_tolerance_is_refined_per_supplier(conn):
    supplier, other = new_uuid(), new_uuid()
    set_setting(conn, "procurement.tolerance.price", "1")
    set_setting(conn, "procurement.tolerance.price", "3", scope_type=ScopeType.SUPPLIER,
                scope_id=supplier)
    service = ProcurementToleranceSettingsQueryService(conn)
    assert service.invoice_tolerances(supplier_id=supplier).price.percentage == Decimal("3")
    assert service.invoice_tolerances(supplier_id=other).price.percentage == Decimal("1")


# ── escritura desde la pantalla de cada módulo ─────────────────────────────
def test_a_module_screen_cannot_bypass_approval(conn, critical):
    with pytest.raises(ConfigurationApprovalRequiredError):
        GovernedSettingsWriter(conn).stage({critical: True}, actor_user_id=new_uuid(),
                                           reason="pantalla", operation_id=new_uuid())


def test_repeating_the_same_change_creates_no_new_version(conn):
    set_setting(conn, TOL, "6")
    set_setting(conn, TOL, "6")
    assert conn.execute("SELECT COUNT(*) FROM configuration_values").fetchone()[0] == 1


def test_changes_are_audited_and_events_are_published_after_commit(conn):
    op = new_uuid()
    seen = []
    handler = lambda payload: seen.append((payload["event_name"], payload["key"]))  # noqa: E731
    get_bus().subscribe(ConfigurationEvents.ACTIVATED, handler, priority=30)
    writer = GovernedSettingsWriter(conn)
    try:
        writer.stage({TOL: "9"}, actor_user_id=new_uuid(), reason="prueba", operation_id=op)
        assert seen == []  # nada se publica antes del commit
        conn.commit()
        writer.publish()
    finally:
        get_bus().unsubscribe(ConfigurationEvents.ACTIVATED, handler)
    assert seen == [(ConfigurationEvents.ACTIVATED, TOL)]
    acciones = [r[0] for r in conn.execute(
        "SELECT action FROM configuracion_audit_log WHERE operation_id=? ORDER BY occurred_at",
        (op,))]
    assert acciones == ["CREAR", "ACTIVAR"]
    after = json.loads(conn.execute(
        "SELECT after_json FROM configuracion_audit_log WHERE action='ACTIVAR'").fetchone()[0])
    assert (after["key"], after["value"], after["status"]) == (TOL, "9", "ACTIVE")


# ── migración 303 ───────────────────────────────────────────────────────────
_m303 = importlib.import_module("migrations.standalone.303_configuration_governance_live")


def test_303_moves_values_renames_keys_and_drops_the_old_rows(conn):
    conn.executemany("INSERT OR REPLACE INTO configuraciones (clave, valor) VALUES (?,?)", [
        ("loyalty_pesos_por_punto", "25"), ("loyalty_credito_acumula", "0"),
        ("loyalty_valor_estrella", "no-es-numero"),
        ("procurement.tolerance.price.default", "2"),
        (f"meat_processing.yield.tolerance_pct@PRODUCT:{(producto := new_uuid())}", "4"),
    ])
    conn.commit()
    _m303.run(conn)
    reader = ConfigurationReader(conn)
    assert reader.get("loyalty.pesos_per_point") == Decimal("25")
    assert reader.get("loyalty.credit_earns") is False
    assert reader.resolve("loyalty.point_value").is_default  # ilegible: no se migró
    assert reader.get("procurement.tolerance.price") == Decimal("2")
    assert reader.get(TOL, context={ScopeType.PRODUCT: producto}) == Decimal("4")
    restantes = {r[0] for r in conn.execute("SELECT clave FROM configuraciones")}
    assert not restantes & set(_m303.KEY_MAP)
    assert not any(k.startswith("meat_processing.yield") for k in restantes)


def test_303_rebuilds_an_old_check_without_the_new_scopes():
    import sqlite3

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    importlib.import_module(
        "migrations.standalone.208_settings_configuration_governance_schema").run(c)
    sql = c.execute("SELECT sql FROM sqlite_master WHERE name='configuration_values'").fetchone()[0]
    viejo = sql.replace(",'SPECIES','WORK_CENTER','PRODUCTION_AREA','PLANT','SUPPLIER'", "")
    c.execute("DROP TABLE configuration_values")
    c.execute(viejo)
    importlib.import_module("migrations.standalone.224_configuracion_security_schema").run(c)
    _m303.run(c)
    assert "SUPPLIER" in c.execute(
        "SELECT sql FROM sqlite_master WHERE name='configuration_values'").fetchone()[0]
    set_setting(c, TOL, "11", scope_type=ScopeType.SPECIES, scope_id=new_uuid())


def _definition_id(conn, key):
    return conn.execute("SELECT id FROM configuration_definitions WHERE key=?", (key,)).fetchone()[0]


# ── fuente única (§76) ──────────────────────────────────────────────────────
def test_no_code_reads_a_governed_parameter_from_configuraciones():
    keys = {spec.key for spec in SETTINGS_CATALOG} | set(_m303.KEY_MAP)
    offenders = []
    for root in ("backend", "frontend"):
        for path in (APP / root).rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if not any(f'"{k}"' in text or f"'{k}'" in text for k in keys):
                continue
            if any(sql in text for sql in ("FROM configuraciones", "INTO configuraciones",
                                           "UPDATE configuraciones")):
                offenders.append(str(path.relative_to(APP)))
    assert not offenders, offenders


def test_configuracion_has_no_screen_for_business_parameters():
    """Decisión del usuario (2026-10-04): Configuración no controla nada que ya
    exista en otro módulo. Los parámetros del catálogo se editan sólo en la
    pantalla de su módulo; dos pantallas para lo mismo se contradicen."""
    keys = {spec.key for spec in SETTINGS_CATALOG}
    offenders = []
    for path in (APP / "frontend" / "desktop" / "modules" / "configuracion").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "GovernedSettingsWriter" in text or "backend.application.settings" in text \
                or any(f'"{k}"' in text for k in keys):
            offenders.append(str(path.relative_to(APP)))
    assert not offenders, offenders
