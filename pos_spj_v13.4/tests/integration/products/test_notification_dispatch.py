"""PROD-16 — notificaciones y WhatsApp: de librería probada-en-aislamiento a
disparador real.

Antes de esta fase, `detect_product_alerts`/`ProductNotificationService`
tenían cobertura de tests unitarios pero CERO puntos de disparo reales
(confirmado por grep) — nada en la aplicación los llamaba nunca. Y
`ProductNotificationGateway` sólo tenía `InMemoryProductNotifier` (doble de
test) como implementación — sin canal real a WhatsApp ni al inbox interno.
Estos tests prueban la cadena completa: crear un producto incompleto →
detectar la alerta → entregarla realmente (inbox interno vía
`InAppProductNotifier`, WhatsApp vía `WhatsAppProductNotifier` sobre el
`WhatsAppService` real) → quedar registrada en `product_notification_log`.
"""

from __future__ import annotations

import sqlite3

import pytest

from backend.application.products.authorization.policy import ProductsAuthorizationPolicy
from backend.application.products.commands.product_master_commands import (
    CreateProductMasterCommand,
)
from backend.application.products.notifications.notification_service import (
    ProductNotificationService,
)
from backend.application.products.permissions import ProductPermissions
from backend.application.products.use_cases.product_master_use_cases import (
    CreateProductMasterUseCase,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.notifications.in_app_product_notifier import (
    InAppProductNotifier,
)
from backend.infrastructure.notifications.product_notification_gateway import (
    FanOutProductNotificationGateway,
)
from backend.infrastructure.notifications.whatsapp_product_notifier import (
    WhatsAppProductNotifier,
)

_P = ProductPermissions
_UNIT = "unit-pza"


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    # notification_inbox / usuarios viven en el esquema legacy (m000); un
    # fixture mínimo de sólo Productos no las trae — se crean aquí para el
    # notifier real, igual que otros tests de integración de Productos que
    # cruzan hacia tablas legacy (p.ej. mermas en test_legacy_repoint_*).
    c.execute("""CREATE TABLE IF NOT EXISTS notification_inbox (
        id TEXT PRIMARY KEY, empleado_id TEXT NOT NULL, tipo TEXT NOT NULL,
        titulo TEXT NOT NULL, cuerpo TEXT DEFAULT '', datos TEXT DEFAULT '{}',
        sucursal_id TEXT, leido INTEGER DEFAULT 0, leido_at TEXT,
        created_at TEXT DEFAULT (datetime('now')))""")
    # whatsapp_queue: schema real vive en migrations/ (WhatsAppService._init_table
    # deliberadamente no la crea, "Plan B born-clean"); un fixture mínimo la trae
    # aquí igual que notification_inbox arriba.
    c.execute("""CREATE TABLE IF NOT EXISTS whatsapp_queue (
        id TEXT PRIMARY KEY, to_number TEXT NOT NULL, message TEXT NOT NULL,
        template TEXT, payload TEXT, estado TEXT DEFAULT 'pendiente',
        intentos INTEGER DEFAULT 0, error TEXT,
        fecha TEXT DEFAULT (datetime('now')), enviado_en TEXT,
        proxima_revision TEXT)""")
    c.execute("INSERT INTO units_of_measure (id, code, name, dimension, active) "
              "VALUES (?, 'PZA', 'Pieza', 'COUNT', 1)", (_UNIT,))
    c.commit()
    yield c
    c.close()


class _Checker:
    def has_permission(self, user_id, code):
        return True


def _auth():
    return ProductsAuthorizationPolicy(_Checker())


class TestInAppNotifierReal:
    def test_writes_real_inbox_row(self, conn):
        notifier = InAppProductNotifier(conn)
        notifier.send(channel="IN_APP", recipient_ref="user-1",
                      message="Producto incompleto", context={"branch_id": "b1"})
        conn.commit()
        row = conn.execute("SELECT empleado_id, cuerpo, sucursal_id FROM "
                           "notification_inbox").fetchone()
        assert row["empleado_id"] == "user-1"
        assert row["cuerpo"] == "Producto incompleto"
        assert row["sucursal_id"] == "b1"


class TestWhatsAppNotifierReal:
    def test_enqueues_via_real_whatsapp_service(self, conn, monkeypatch):
        # Neutraliza sólo el spawn del hilo worker en background (tocaría esta
        # conexión :memory: desde otro hilo, insegura tras el teardown del
        # fixture) — el encolado real (`MessageQueue.enqueue`) SÍ corre sin doble.
        from core.services.whatsapp_service import WhatsAppService
        monkeypatch.setattr(WhatsAppService, "_ensure_worker", lambda self: None)

        notifier = WhatsAppProductNotifier(conn)
        notifier.send(channel="WHATSAPP", recipient_ref="5215512345678",
                      message="Alerta crítica de producto", context={})
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM whatsapp_queue WHERE to_number='5215512345678'"
        ).fetchone()
        assert row["n"] >= 1


class TestNotificationDispatchOnProductCreate:
    def test_incomplete_product_triggers_in_app_alert(self, conn):
        gateway = FanOutProductNotificationGateway(conn)
        service = ProductNotificationService(conn, gateway=gateway)
        r = CreateProductMasterUseCase(
            conn, _auth(), notification_service=service,
            notify_recipients=["user-1"]).execute(CreateProductMasterCommand(
                operation_id="op", code="A-1", name="Producto sin categoría",
                product_type="RAW_MATERIAL", base_unit_id=_UNIT,
                category_id=None, user_id="u1"))
        assert r.success
        rows = conn.execute(
            "SELECT alert_type, status FROM product_notification_log "
            "WHERE entity_id=?", (r.product_id,)).fetchall()
        assert any(row["alert_type"] == "PRODUCT_INCOMPLETE" and row["status"] == "SENT"
                  for row in rows)
        inbox = conn.execute("SELECT COUNT(*) AS n FROM notification_inbox").fetchone()
        assert inbox["n"] >= 1

    def test_complete_product_triggers_no_alert(self, conn):
        gateway = FanOutProductNotificationGateway(conn)
        service = ProductNotificationService(conn, gateway=gateway)
        r = CreateProductMasterUseCase(
            conn, _auth(), notification_service=service,
            notify_recipients=["user-1"]).execute(CreateProductMasterCommand(
                operation_id="op", code="A-2", name="Producto completo",
                product_type="RESALE_PRODUCT", base_unit_id=_UNIT,
                category_id="cat-1", user_id="u1"))
        assert r.success
        rows = conn.execute(
            "SELECT 1 FROM product_notification_log WHERE entity_id=?",
            (r.product_id,)).fetchall()
        assert rows == []

    def test_no_notification_service_is_a_true_noop(self, conn):
        # Comportamiento por defecto (sin wiring de notificaciones): idéntico
        # a antes de esta fase — ni siquiera se consulta product_notification_log.
        r = CreateProductMasterUseCase(conn, _auth()).execute(
            CreateProductMasterCommand(
                operation_id="op", code="A-3", name="Producto sin categoría",
                product_type="RAW_MATERIAL", base_unit_id=_UNIT,
                category_id=None, user_id="u1"))
        assert r.success
        rows = conn.execute(
            "SELECT 1 FROM product_notification_log WHERE entity_id=?",
            (r.product_id,)).fetchall()
        assert rows == []

    def test_perishable_without_shelf_life_profile_triggers_alert(self, conn):
        # A diferencia de especie (bloqueada en creación por validate_creation,
        # confirmado al escribir este test — MEAT_WITHOUT_SPECIES resultó
        # inalcanzable vía este caso de uso), un producto con
        # expiration_controlled=True SÍ puede crearse sin perfil de vida útil
        # todavía — exactamente el estado "incompleto" que la alerta detecta.
        gateway = FanOutProductNotificationGateway(conn)
        service = ProductNotificationService(conn, gateway=gateway)
        r = CreateProductMasterUseCase(
            conn, _auth(), notification_service=service,
            notify_recipients=["user-1"]).execute(CreateProductMasterCommand(
                operation_id="op", code="A-4", name="Producto perecedero",
                product_type="RESALE_PRODUCT", base_unit_id=_UNIT,
                category_id="cat-1", expiration_controlled=True, user_id="u1"))
        assert r.success
        rows = conn.execute(
            "SELECT alert_type FROM product_notification_log WHERE entity_id=?",
            (r.product_id,)).fetchall()
        assert any(row["alert_type"] == "PERISHABLE_WITHOUT_SHELF_LIFE"
                  for row in rows)
