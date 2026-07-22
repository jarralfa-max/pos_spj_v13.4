"""INV-23 — notifications: routing, severity gate, idempotency, throttle, audit."""

from datetime import datetime, timedelta, timezone

import sqlite3

import pytest

from backend.application.inventory.authorization import InventoryAuthorizationPolicy
from backend.application.inventory.notifications import (
    InMemoryNotificationGateway,
    InventoryNotificationService,
    SetNotificationRuleUseCase,
)
from backend.domain.inventory.enums import (
    NotificationChannel,
    NotificationRecipientType,
    NotificationSeverity,
)
from backend.domain.inventory.events import InventoryEvents
from backend.infrastructure.db.repositories.inventory.unit_of_work import (
    InventoryUnitOfWork,
)
from backend.infrastructure.db.schema.inventory_schema import create_inventory_schema

T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_inventory_schema(c)
    c.commit()
    yield c
    c.close()


def _rule(conn, **kw):
    base = dict(event_name="INVENTORY_STOCK_LOW", channel=NotificationChannel.WHATSAPP,
                recipient_type=NotificationRecipientType.PHONE, recipient_ref="+52155",
                actor_user_id="mgr", min_severity=NotificationSeverity.WARNING)
    base.update(kw)
    return SetNotificationRuleUseCase().execute(conn, **base)


def _event(event_id="e1", name="INVENTORY_STOCK_LOW", **kw):
    base = {"event_id": event_id, "event_name": name, "branch_id": "b1",
            "warehouse_id": "w1", "product_id": "p1"}
    base.update(kw)
    return base


class TestNotify:
    def test_matching_rule_delivers_and_logs_and_emits(self, conn):
        _rule(conn)
        gw = InMemoryNotificationGateway()
        res = InventoryNotificationService(gw).notify(conn, _event(), now=_iso(T0))
        assert res.success and res.data["sent"] == 1
        assert len(gw.delivered) == 1 and gw.delivered[0]["recipient_ref"] == "+52155"
        with InventoryUnitOfWork(conn) as uow:
            log = uow.notification_log.list_for_event("e1")
            assert log[0]["status"] == "SENT"
            events = {p["event_name"] for p in uow.outbox.list_pending()}
            assert InventoryEvents.INVENTORY_NOTIFICATION_CREATED in events
            assert InventoryEvents.INVENTORY_WHATSAPP_ALERT_SENT in events

    def test_same_event_is_idempotent(self, conn):
        _rule(conn)
        gw = InMemoryNotificationGateway()
        svc = InventoryNotificationService(gw)
        svc.notify(conn, _event(), now=_iso(T0))
        res = svc.notify(conn, _event(), now=_iso(T0))  # replay same event_id
        assert res.data["deduped"] == 1 and len(gw.delivered) == 1

    def test_below_min_severity_is_suppressed(self, conn):
        _rule(conn, min_severity=NotificationSeverity.CRITICAL)  # STOCK_LOW is WARNING
        gw = InMemoryNotificationGateway()
        res = InventoryNotificationService(gw).notify(conn, _event(), now=_iso(T0))
        assert res.data["suppressed"] == 1 and gw.delivered == []

    def test_throttle_suppresses_repeat_within_window(self, conn):
        _rule(conn, throttle_seconds=3600)
        gw = InMemoryNotificationGateway()
        svc = InventoryNotificationService(gw)
        svc.notify(conn, _event("e1"), now=_iso(T0))                       # SENT
        res = svc.notify(conn, _event("e2"), now=_iso(T0 + timedelta(seconds=60)))
        assert res.data["throttled"] == 1 and len(gw.delivered) == 1
        # outside the window it flows again
        res2 = svc.notify(conn, _event("e3"), now=_iso(T0 + timedelta(seconds=3601)))
        assert res2.data["sent"] == 1 and len(gw.delivered) == 2

    def test_branch_scope_only_matches_that_branch(self, conn):
        _rule(conn, scope_type="BRANCH", scope_id="b1")
        gw = InMemoryNotificationGateway()
        svc = InventoryNotificationService(gw)
        assert svc.notify(conn, _event("e1", branch_id="b1"), now=_iso(T0)).data["sent"] == 1
        assert svc.notify(conn, _event("e2", branch_id="b2"), now=_iso(T0)).data["sent"] == 0

    def test_delivery_failure_is_logged_not_raised(self, conn):
        _rule(conn)

        class FailingGateway:
            def send(self, **kw):
                raise RuntimeError("whatsapp down")

        res = InventoryNotificationService(FailingGateway()).notify(
            conn, _event(), now=_iso(T0))
        assert res.data["failed"] == 1 and res.data["sent"] == 0
        with InventoryUnitOfWork(conn) as uow:
            assert uow.notification_log.list_for_event("e1")[0]["status"] == "FAILED"
            # no NOTIFICATION_CREATED emitted on failure
            assert uow.outbox.list_pending() == []


class TestRulePermissions:
    def test_whatsapp_rule_requires_whatsapp_permission(self, conn):
        class Denies:
            def has_permission(self, u, p):
                return False
        res = SetNotificationRuleUseCase(InventoryAuthorizationPolicy(Denies())).execute(
            conn, event_name="INVENTORY_STOCK_LOW", channel=NotificationChannel.WHATSAPP,
            recipient_type=NotificationRecipientType.PHONE, recipient_ref="+52155",
            actor_user_id="clerk")
        assert not res.success and res.error_code == "PERMISSION_DENIED"
