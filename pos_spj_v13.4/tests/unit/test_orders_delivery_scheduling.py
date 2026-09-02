"""ORD-6 — scheduled orders (§19): CustomerOrder.schedule()/reschedule()/
activate_schedule()/cancel_schedule() and ScheduledOrderPolicy."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.domain.orders_delivery.enums import (
    FulfillmentType,
    OrderChannel,
    OrderType,
    ScheduleStatus,
)
from backend.domain.orders_delivery.entities import CustomerOrder
from backend.domain.orders_delivery.exceptions import (
    InvalidOrderScheduleError,
    OrderActivationNotDueError,
)
from backend.shared.ids import new_uuid


def _order() -> CustomerOrder:
    return CustomerOrder.create(
        branch_id=new_uuid(), channel=OrderChannel.WHATSAPP, order_type=OrderType.SCHEDULED,
        fulfillment_type=FulfillmentType.SCHEDULED_DELIVERY,
    )


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


class TestSchedule:
    def test_schedule_sets_status_scheduled(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now + timedelta(days=1)),
            window_start=_iso(now + timedelta(days=1)),
            window_end=_iso(now + timedelta(days=1, hours=2)),
            activation_at=_iso(now + timedelta(hours=12)))
        assert order.schedule_status == ScheduleStatus.SCHEDULED

    def test_schedule_rejects_inverted_window(self):
        order = _order()
        now = datetime.now(timezone.utc)
        with pytest.raises(InvalidOrderScheduleError):
            order.schedule(
                scheduled_for=_iso(now), window_start=_iso(now + timedelta(hours=2)),
                window_end=_iso(now), activation_at=_iso(now))

    def test_schedule_rejects_missing_window(self):
        order = _order()
        with pytest.raises(InvalidOrderScheduleError):
            order.schedule(scheduled_for="x", window_start="", window_end="", activation_at="x")


class TestActivation:
    def test_activate_when_due(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now - timedelta(minutes=5)))
        order.activate_schedule(now=now)
        assert order.schedule_status == ScheduleStatus.ACTIVATED

    def test_activate_before_due_raises(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now + timedelta(hours=1)))
        with pytest.raises(OrderActivationNotDueError):
            order.activate_schedule(now=now)

    def test_activate_without_schedule_raises(self):
        order = _order()
        with pytest.raises(InvalidOrderScheduleError):
            order.activate_schedule(now=datetime.now(timezone.utc))

    def test_double_activation_raises(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now - timedelta(minutes=5)))
        order.activate_schedule(now=now)
        with pytest.raises(InvalidOrderScheduleError):
            order.activate_schedule(now=now)


class TestReschedule:
    def test_reschedule_updates_window_and_status(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now))
        new_start = _iso(now + timedelta(days=2))
        new_end = _iso(now + timedelta(days=2, hours=1))
        order.reschedule(scheduled_for=new_start, window_start=new_start, window_end=new_end,
                          activation_at=new_start)
        assert order.schedule_status == ScheduleStatus.RESCHEDULED
        assert order.delivery_window_start == new_start

    def test_cannot_reschedule_activated_order(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now - timedelta(minutes=1)))
        order.activate_schedule(now=now)
        with pytest.raises(InvalidOrderScheduleError):
            order.reschedule(scheduled_for=_iso(now), window_start=_iso(now),
                              window_end=_iso(now + timedelta(hours=1)), activation_at=_iso(now))


class TestCancelSchedule:
    def test_cancel_schedule(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now))
        order.cancel_schedule()
        assert order.schedule_status == ScheduleStatus.CANCELLED

    def test_cannot_cancel_activated_schedule(self):
        order = _order()
        now = datetime.now(timezone.utc)
        order.schedule(
            scheduled_for=_iso(now), window_start=_iso(now), window_end=_iso(now + timedelta(hours=1)),
            activation_at=_iso(now - timedelta(minutes=1)))
        order.activate_schedule(now=now)
        with pytest.raises(InvalidOrderScheduleError):
            order.cancel_schedule()
