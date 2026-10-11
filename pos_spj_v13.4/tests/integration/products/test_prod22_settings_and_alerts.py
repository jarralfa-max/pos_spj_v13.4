"""PROD-22 (pendientes) — Productos → Configuración y alertas del §35/§36.

Antes las alertas existían (detectores, servicio, campana, WhatsApp) pero nunca
se disparaban: nadie pasaba servicio ni destinatarios, y la lista de
destinatarios era una sola para dos canales con direcciones distintas.
"""

from __future__ import annotations

import importlib
import os
import sqlite3

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from backend.application.products.queries.product_settings_query import (  # noqa: E402
    ProductSettingsQuery,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema  # noqa: E402
from backend.infrastructure.db.schema.pricing_schema import create_pricing_schema  # noqa: E402
from backend.infrastructure.db.schema.products_schema import create_products_schema  # noqa: E402

ALL = {f"PRODUCTOS.{a}" for a in importlib.import_module(
    "migrations.standalone.324_seed_products_granular_permissions")._TODAS}


class _Session:
    def __init__(self, user_id="u-dueno", codes=ALL):
        self.user_id = user_id
        self._codes = set(codes)
        self.sucursal_id = None
        self.is_active = True

    def tiene_permiso(self, code):
        return code in self._codes


@pytest.fixture(scope="module")
def qapp():
    from PyQt5.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    from tests.integration._governed_settings import ensure_governance
    ensure_governance(c)
    importlib.import_module("migrations.standalone.329_products_settings_catalog").run(c)
    create_products_schema(c)
    create_pricing_schema(c)
    create_inventory_schema(c)
    c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios (id TEXT PRIMARY KEY, nombre TEXT, usuario TEXT,
                                             rol TEXT, activo INTEGER DEFAULT 1);
        INSERT INTO usuarios VALUES ('u-dueno','Dueña','d','system_owner',1),
                                    ('u-ger','Gerente','g','gerente',1),
                                    ('u-caj','Cajero','c','cajero',1),
                                    ('u-baja','Ex gerente','x','gerente',0);
        CREATE TABLE IF NOT EXISTS notification_inbox (id TEXT PRIMARY KEY, empleado_id TEXT,
            tipo TEXT, titulo TEXT, cuerpo TEXT, datos TEXT, sucursal_id TEXT, created_at TEXT);
        INSERT INTO units_of_measure (id, code, name, dimension) VALUES
            ('u-kg','KG','Kilogramo','WEIGHT'), ('u-pza','PZA','Pieza','COUNT');
        INSERT INTO species (id, code, name, active) VALUES ('sp','AVE_POLLO','Ave',1);
    """)
    c.commit()
    yield c
    c.close()


@pytest.fixture(autouse=True)
def whatsapp_sent(monkeypatch):
    """Intercepta el envío real de WhatsApp (sin red)."""
    sent = []
    from backend.infrastructure.integrations import whatsapp_client
    monkeypatch.setattr(whatsapp_client.WhatsAppClient, "enviar_mensaje",
                        lambda self, phone, message: sent.append((phone, message)) or True)
    return sent


def _presenter(conn, user_id="u-dueno", codes=ALL):
    from frontend.desktop.modules.products.composition import (
        _Session as LiveSession,
        build_products_presenter,
    )
    live = _Session(user_id, codes)
    return build_products_presenter(conn, LiveSession(live), live_session=live)


def _create_incomplete(presenter, name="Retazo", ptype="TRIM"):
    return presenter.save_product(product_id=None, fields={
        "name": name, "product_type": ptype, "base_unit_id": "u-kg", "species_id": "sp",
        "auto_generate_code": True, "code": ""})


def test_defaults_reproduce_todays_behavior(conn):
    s = ProductSettingsQuery(conn).current()
    assert s.alerts_enabled is False and s.whatsapp_enabled is False
    assert s.default_product_type == "RESALE_PRODUCT" and s.default_base_unit_code == ""


def test_no_alert_is_sent_while_alerts_are_off(conn):
    assert _create_incomplete(_presenter(conn))[0]
    assert conn.execute("SELECT COUNT(*) FROM notification_inbox").fetchone()[0] == 0


def test_enabled_alerts_reach_the_bell_of_active_users_with_the_roles(conn, whatsapp_sent):
    p = _presenter(conn)
    assert p.settings.save(alerts={"enabled": True, "roles": "system_owner, gerente"})[0]
    assert _create_incomplete(p)[0]
    inbox = {r[0] for r in conn.execute("SELECT empleado_id FROM notification_inbox")}
    assert inbox == {"u-dueno", "u-ger"}          # ni cajero ni el gerente dado de baja
    log = p.settings.notification_log()
    assert {r["channel"] for r in log} == {"IN_APP"}
    assert whatsapp_sent == []


def test_whatsapp_goes_to_phones_only_and_only_for_high_impact(conn, whatsapp_sent):
    p = _presenter(conn)
    p.settings.save(alerts={"enabled": True, "roles": "system_owner"},
                    whatsapp={"enabled": True, "phones": "5215512345678"})
    assert _create_incomplete(p)[0]              # «incompleto» no es de alto impacto
    assert whatsapp_sent == []
    inbox = [r[0] for r in conn.execute("SELECT empleado_id FROM notification_inbox")]
    assert "5215512345678" not in inbox          # un teléfono nunca va a la campana


def test_whatsapp_needs_a_phone(conn):
    ok, message = _presenter(conn).settings.save(whatsapp={"enabled": True, "phones": ""})
    assert not ok and "teléfono" in message


def test_each_settings_group_needs_its_permission(conn):
    manager = _presenter(conn, "u-ger", codes={"PRODUCTOS.ver", "PRODUCTOS.configuracion.ver"})
    assert not manager.settings.can_edit_alerts
    ok, _ = manager.settings.save(alerts={"enabled": True, "roles": "gerente"})
    assert not ok and ProductSettingsQuery(conn).current().alerts_enabled is False


def test_settings_changes_are_audited_without_exposing_phones(conn):
    _presenter(conn).settings.save(alerts={"enabled": True, "roles": "admin"},
                                   whatsapp={"enabled": True, "phones": "5215512345678"})
    row = conn.execute("SELECT after FROM product_audit_log "
                       "WHERE action='PRODUCT_SETTINGS_UPDATED'").fetchone()
    assert row is not None and "5215512345678" not in row[0]


def test_new_product_form_uses_the_configured_defaults(conn, qapp):
    from frontend.desktop.modules.products.dialogs.product_form_dialog import ProductFormDialog
    p = _presenter(conn)
    p.settings.save(defaults={"product_type": "PRIMARY_CUT", "base_unit_code": "kg"})
    form = ProductFormDialog(p)
    assert form.product_type.currentData() == "PRIMARY_CUT"
    assert form._combo_value(form.base_unit) == "u-kg"


def test_settings_and_notifications_pages_open(conn, qapp):
    from frontend.desktop.modules.products.pages.notifications_page import (
        ProductNotificationsPage,
    )
    from frontend.desktop.modules.products.pages.settings_page import ProductSettingsPage
    p = _presenter(conn)
    p.settings.save(alerts={"enabled": True, "roles": "system_owner"})
    _create_incomplete(p)
    page = ProductSettingsPage(p)
    assert page.alerts_enabled.isChecked() and page.btn_whatsapp.isEnabled()
    notifications = ProductNotificationsPage(p)
    assert notifications.table.rowCount() >= 1
    assert "activas" in notifications.state.text()


def test_high_impact_alert_is_sent_by_whatsapp_to_the_configured_phone(conn, whatsapp_sent):
    p = _presenter(conn)
    p.settings.save(alerts={"enabled": True, "roles": "system_owner"},
                    whatsapp={"enabled": True, "phones": "5215512345678"})
    ok, message, _pid = p.save_product(product_id=None, fields={
        "name": "Pechuga sin perfil", "product_type": "PRIMARY_CUT", "base_unit_id": "u-kg",
        "species_id": "sp", "auto_generate_code": True, "code": "",
        "quality_controlled": True})
    assert ok, message
    # Cola en el ERP: nada sale a la red dentro de la operación; se encola.
    assert whatsapp_sent == []
    queue = p.settings.whatsapp_queue()
    assert [(q["recipient"], q["status"]) for q in queue] == [("•••• 5678", "PENDING")]
    from backend.application.products.notifications.whatsapp_outbox import (
        drain_product_whatsapp_outbox,
    )
    assert drain_product_whatsapp_outbox(conn)["sent"] == 1
    assert [phone for phone, _msg in whatsapp_sent] == ["5215512345678"]
    assert p.settings.whatsapp_queue()[0]["status"] == "SENT"
    log = p.settings.notification_log()
    whatsapp_rows = [r for r in log if r["channel"] == "WHATSAPP"]
    assert whatsapp_rows and whatsapp_rows[0]["recipient"] == "•••• 5678"
