"""PROD-16 — notificaciones/WhatsApp: policy, gateway, throttle, detectores, audit."""

import sqlite3

import pytest

from backend.application.products.notification_handlers.product_alert_detectors import (
    detect_discontinued_still_active,
    detect_product_alerts,
)
from backend.application.products.notifications.gateway import (
    InMemoryProductNotifier,
    NotificationDeliveryError,
)
from backend.application.products.notifications.notification_policy import (
    channels_for,
    is_high_impact,
    severity_for,
)
from backend.application.products.notifications.notification_service import (
    ProductNotificationService,
)
from backend.domain.products.entities.product import Product
from backend.domain.products.enums import ProductType
from backend.domain.products.notification_enums import (
    NotificationChannel,
    NotificationSeverity,
    ProductAlertType,
)
from backend.infrastructure.db.schema.products_schema import create_products_schema


# ── policy (§35, §36) ────────────────────────────────────────────────────────
class TestPolicy:
    def test_severity_mapping(self):
        assert severity_for(ProductAlertType.QUALITY_BLOCKED) is NotificationSeverity.CRITICAL
        assert severity_for(ProductAlertType.PENDING_APPROVAL) is NotificationSeverity.INFO

    def test_whatsapp_only_high_impact(self):
        wa = channels_for(ProductAlertType.QUALITY_BLOCKED)
        assert NotificationChannel.WHATSAPP in wa
        low = channels_for(ProductAlertType.PENDING_APPROVAL)
        assert NotificationChannel.WHATSAPP not in low
        assert NotificationChannel.IN_APP in low

    def test_whatsapp_disabled_globally(self):
        wa = channels_for(ProductAlertType.QUALITY_BLOCKED, whatsapp_enabled=False)
        assert NotificationChannel.WHATSAPP not in wa

    def test_is_high_impact(self):
        assert is_high_impact(ProductAlertType.RECIPE_CIRCULAR)
        assert not is_high_impact(ProductAlertType.RECIPE_VERSION_EXPIRING)


# ── detectors (§35) ──────────────────────────────────────────────────────────
class TestDetectors:
    def test_meat_without_species_and_incomplete(self):
        p = Product(code="CUT-1", name="Corte", product_type=ProductType.PRIMARY_CUT,
                    base_unit_id="kg", category_id=None, species_id=None)
        alerts = detect_product_alerts(p)
        assert ProductAlertType.MEAT_WITHOUT_SPECIES in alerts
        assert ProductAlertType.PRODUCT_INCOMPLETE in alerts

    def test_perishable_without_shelf_life(self):
        p = Product(code="MEAT-1", name="Pollo", product_type=ProductType.PRIMARY_CUT,
                    base_unit_id="kg", category_id="c1", species_id="sp1",
                    expiration_controlled=True)
        assert ProductAlertType.PERISHABLE_WITHOUT_SHELF_LIFE in \
            detect_product_alerts(p, has_shelf_life_profile=False)
        assert ProductAlertType.PERISHABLE_WITHOUT_SHELF_LIFE not in \
            detect_product_alerts(p, has_shelf_life_profile=True)

    def test_meat_without_quality_profile(self):
        p = Product(code="MEAT-2", name="Res", product_type=ProductType.PRIMARY_CUT,
                    base_unit_id="kg", category_id="c1", species_id="sp1",
                    quality_controlled=True)
        assert ProductAlertType.MEAT_WITHOUT_QUALITY_PROFILE in \
            detect_product_alerts(p, has_quality_profile=False)

    def test_catch_weight_without_range(self):
        p = Product(code="CW", name="Bistec", product_type=ProductType.PRIMARY_CUT,
                    base_unit_id="kg", category_id="c1", species_id="sp1",
                    catch_weight_enabled=True)
        assert ProductAlertType.CATCH_WEIGHT_WITHOUT_RANGE in \
            detect_product_alerts(p, catch_weight_configured=False)

    def test_clean_product_no_alerts(self):
        p = Product(code="ABR", name="Refresco", product_type=ProductType.RESALE_PRODUCT,
                    base_unit_id="pza", category_id="c1")
        assert detect_product_alerts(p) == []

    def test_discontinued_still_active(self):
        p = Product(code="OLD", name="Viejo", product_type=ProductType.RESALE_PRODUCT,
                    base_unit_id="pza", category_id="c1")
        p.activate(); p.discontinue()
        assert detect_discontinued_still_active(p, enabled_branch_count=2) \
            is ProductAlertType.DISCONTINUED_STILL_ACTIVE
        assert detect_discontinued_still_active(p, enabled_branch_count=0) is None


# ── service: deliver / throttle / audit ──────────────────────────────────────
@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_products_schema(c)
    c.commit()
    yield c
    c.close()


class TestService:
    def test_delivers_in_app_and_whatsapp_and_audits(self, conn):
        gw = InMemoryProductNotifier()
        seen = []
        svc = ProductNotificationService(conn, gateway=gw,
                                         event_dispatcher=lambda n, p: seen.append(n))
        out = svc.notify(ProductAlertType.QUALITY_BLOCKED, entity_id="p1",
                         message="Producto bloqueado por calidad", recipients=["mgr"])
        assert out.sent == 2  # in-app + whatsapp
        channels = {d["channel"] for d in gw.delivered}
        assert channels == {"IN_APP", "WHATSAPP"}
        assert "PRODUCT_WHATSAPP_ALERT_SENT" in seen
        rows = conn.execute("SELECT COUNT(*) c FROM product_notification_log "
                            "WHERE status='SENT'").fetchone()
        assert rows["c"] == 2

    def test_throttle_suppresses_repeat(self, conn):
        svc = ProductNotificationService(conn, gateway=InMemoryProductNotifier(),
                                         throttle_seconds=3600)
        svc.notify(ProductAlertType.PRODUCT_INCOMPLETE, entity_id="p1",
                   message="incompleto", recipients=["mgr"])
        out = svc.notify(ProductAlertType.PRODUCT_INCOMPLETE, entity_id="p1",
                         message="incompleto", recipients=["mgr"])
        assert out.sent == 0 and out.throttled == 1

    def test_low_severity_no_whatsapp(self, conn):
        gw = InMemoryProductNotifier()
        svc = ProductNotificationService(conn, gateway=gw)
        svc.notify(ProductAlertType.PENDING_APPROVAL, entity_id="p1",
                   message="pendiente", recipients=["mgr"])
        assert {d["channel"] for d in gw.delivered} == {"IN_APP"}

    def test_delivery_failure_audited(self, conn):
        class _Bad:
            def send(self, **kw): raise NotificationDeliveryError("wa down")
        svc = ProductNotificationService(conn, gateway=_Bad())
        out = svc.notify(ProductAlertType.PRODUCT_INCOMPLETE, entity_id="p1",
                         message="x", recipients=["mgr"])
        assert out.failed == 1 and out.sent == 0
        row = conn.execute("SELECT status FROM product_notification_log "
                           "ORDER BY created_at DESC LIMIT 1").fetchone()
        assert row["status"] == "FAILED"
