# tests/unit/test_remediacion0_raffle_finance_handler.py
"""Remediación 0 — B1: el handler financiero de rifas debe registrar asientos.

Bug original (core/events/wiring.py): `raffle_id = str(...)` seguido de
`if raffle_id <= 0:` lanzaba TypeError (str vs int), capturado por el
`except` genérico → NINGÚN asiento de rifas se registraba jamás.

Estos tests cablean _wire_raffle_finance_handlers contra un container fake y
verifican que, con un raffle_id UUID válido, el asiento SÍ se registra, y que
con raffle_id vacío NO se registra (sin explotar).
"""
from __future__ import annotations

import pytest

from core.events.event_bus import (
    EventBus,
    RAFFLE_BUDGET_RESERVED,
    RAFFLE_PRIZE_DELIVERED,
    RAFFLE_BUDGET_RELEASED,
)
from core.events.wiring import _wire_raffle_finance_handlers

RAFFLE_EVENTS = (RAFFLE_BUDGET_RESERVED, RAFFLE_PRIZE_DELIVERED, RAFFLE_BUDGET_RELEASED)


class _FakeFinance:
    def __init__(self):
        self.asientos = []

    def registrar_asiento(self, **kwargs):
        self.asientos.append(kwargs)
        return "asiento-uuid"


class _FakeLedgerDB:
    """Simula repo.db para el guard idempotente (INSERT en raffle_financial_ledger)."""

    def __init__(self):
        self.inserts = []

    def execute(self, sql, params=()):
        self.inserts.append((sql, params))
        return None


class _FakeRepo:
    def __init__(self):
        self.db = _FakeLedgerDB()


class _FakeLoyaltyApp:
    def __init__(self):
        self.repo = _FakeRepo()


class _FakeLoyaltyService:
    def __init__(self):
        self._app = _FakeLoyaltyApp()


class _FakeContainer:
    def __init__(self):
        self.finance_service = _FakeFinance()
        self.loyalty_service = _FakeLoyaltyService()


@pytest.fixture()
def bus_and_container():
    bus = EventBus()
    # Aislar los canales de rifas del wiring global de otras suites.
    for evt in RAFFLE_EVENTS:
        bus.clear_handlers(evt)
    container = _FakeContainer()
    _wire_raffle_finance_handlers(bus, container)
    yield bus, container
    for evt in RAFFLE_EVENTS:
        bus.clear_handlers(evt)


def _payload(raffle_id):
    return {
        "raffle_id": raffle_id,
        "referencia": "REF-TEST-001",
        "monto": 150.0,
        "usuario": "tester",
        "sucursal_id": "0198c0de-aaaa-7bbb-8ccc-424242424242",
    }


def test_raffle_budget_reserved_posts_asiento_with_uuid(bus_and_container):
    bus, container = bus_and_container
    raffle_uuid = "0198c0de-1234-7abc-8def-000000000001"

    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(raffle_uuid))

    assert len(container.finance_service.asientos) == 1, (
        "El handler de rifas no registró el asiento con un raffle_id UUID "
        "válido — regresión del bug `str <= 0` (wiring.py)."
    )
    asiento = container.finance_service.asientos[0]
    assert asiento["modulo"] == "raffles"
    assert asiento["monto"] == 150.0
    assert asiento["metadata"]["raffle_id"] == raffle_uuid
    # El guard idempotente también debe haber insertado en el ledger.
    assert container.loyalty_service._app.repo.db.inserts


@pytest.mark.parametrize("evento", RAFFLE_EVENTS)
def test_all_raffle_channels_post(bus_and_container, evento):
    bus, container = bus_and_container
    bus.publish(evento, _payload("0198c0de-1234-7abc-8def-00000000000f"))
    assert len(container.finance_service.asientos) == 1


def test_empty_raffle_id_does_not_post(bus_and_container):
    bus, container = bus_and_container
    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(""))
    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(None))
    assert container.finance_service.asientos == []


def test_wiring_source_has_no_str_int_comparison():
    """Guardrail estático: el patrón roto no debe volver."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    src = (root / "core" / "events" / "wiring.py").read_text(encoding="utf-8")
    assert "if raffle_id <= 0" not in src, (
        "Reapareció la comparación str<=int que silenciaba los asientos de rifas."
    )
