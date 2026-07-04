# tests/unit/test_remediacion0_raffle_finance_handler.py
"""Remediación 0 — B1: el handler financiero de rifas debe registrar asientos.

Bug original (core/events/wiring.py): `raffle_id = str(...)` seguido de
`if raffle_id <= 0:` lanzaba TypeError (str vs int), capturado por el
`except` genérico → NINGÚN asiento de rifas se registraba jamás.

Bug secundario (review Codex P1): los flujos reales insertan el triple
(raffle_id, tipo, referencia) en raffle_financial_ledger DESDE LoyaltyRepository
antes de publicar el evento; la guardia idempotente del handler usaba el mismo
triple, chocaba con el UNIQUE y el asiento se saltaba igualmente. La guardia
ahora usa el namespace 'gl:<tipo>' exclusivo del handler.

Estos tests usan una tabla raffle_financial_ledger REAL (sqlite en memoria,
schema de la migración 113) para reproducir ambos escenarios.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.events.event_bus import (
    EventBus,
    RAFFLE_BUDGET_RESERVED,
    RAFFLE_PRIZE_DELIVERED,
    RAFFLE_BUDGET_RELEASED,
)
from core.events.wiring import _wire_raffle_finance_handlers

RAFFLE_EVENTS = (RAFFLE_BUDGET_RESERVED, RAFFLE_PRIZE_DELIVERED, RAFFLE_BUDGET_RELEASED)

_LEDGER_DDL = """
CREATE TABLE raffle_financial_ledger(
    id TEXT PRIMARY KEY,
    raffle_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    monto REAL DEFAULT 0,
    referencia TEXT NOT NULL,
    descripcion TEXT DEFAULT '',
    usuario TEXT DEFAULT '',
    sucursal_id TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(raffle_id, tipo, referencia)
);
"""


class _FakeFinance:
    def __init__(self):
        self.asientos = []

    def registrar_asiento(self, **kwargs):
        self.asientos.append(kwargs)
        return "asiento-uuid"


class _FakeRepo:
    def __init__(self, conn):
        self.db = conn


class _FakeLoyaltyApp:
    def __init__(self, conn):
        self.repo = _FakeRepo(conn)


class _FakeLoyaltyService:
    def __init__(self, conn):
        self._app = _FakeLoyaltyApp(conn)


class _FakeContainer:
    def __init__(self, conn):
        self.finance_service = _FakeFinance()
        self.loyalty_service = _FakeLoyaltyService(conn)


@pytest.fixture()
def entorno():
    conn = sqlite3.connect(":memory:")
    conn.execute(_LEDGER_DDL)
    bus = EventBus()
    # Aislar los canales de rifas del wiring global de otras suites.
    for evt in RAFFLE_EVENTS:
        bus.clear_handlers(evt)
    container = _FakeContainer(conn)
    _wire_raffle_finance_handlers(bus, container)
    yield bus, container, conn
    for evt in RAFFLE_EVENTS:
        bus.clear_handlers(evt)
    conn.close()


def _payload(raffle_id, referencia="REF-TEST-001"):
    return {
        "raffle_id": raffle_id,
        "referencia": referencia,
        "monto": 150.0,
        "usuario": "tester",
        "sucursal_id": "0198c0de-aaaa-7bbb-8ccc-424242424242",
    }


RAFFLE_UUID = "0198c0de-1234-7abc-8def-000000000001"


def test_raffle_budget_reserved_posts_asiento_with_uuid(entorno):
    bus, container, conn = entorno

    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(RAFFLE_UUID))

    assert len(container.finance_service.asientos) == 1, (
        "El handler de rifas no registró el asiento con un raffle_id UUID "
        "válido — regresión del bug `str <= 0` (wiring.py)."
    )
    asiento = container.finance_service.asientos[0]
    assert asiento["modulo"] == "raffles"
    assert asiento["monto"] == 150.0
    assert asiento["metadata"]["raffle_id"] == RAFFLE_UUID
    # La guardia del handler usa el namespace gl: y acuña id no-NULL.
    row = conn.execute(
        "SELECT id, tipo FROM raffle_financial_ledger WHERE tipo LIKE 'gl:%'"
    ).fetchone()
    assert row is not None and row[0], "La fila-guardia gl: debe existir con id UUID no NULL"
    assert row[1] == "gl:budget_reserved"


def test_asiento_se_registra_aunque_el_repo_ya_insertara_el_ledger(entorno):
    """Regresión del review Codex P1: en el flujo real LoyaltyRepository inserta
    (raffle_id, 'budget_reserved', referencia) ANTES de publicar el evento.
    El asiento debe registrarse igualmente."""
    bus, container, conn = entorno
    conn.execute(
        "INSERT INTO raffle_financial_ledger (id, raffle_id, tipo, monto, referencia)"
        " VALUES ('fila-del-repo', ?, 'budget_reserved', 150.0, 'REF-TEST-001')",
        (RAFFLE_UUID,),
    )

    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(RAFFLE_UUID))

    assert len(container.finance_service.asientos) == 1, (
        "Con la fila base del repo ya insertada, la guardia del handler chocaba "
        "con el UNIQUE y el asiento se saltaba (review Codex P1)."
    )


def test_redelivery_no_duplica_asiento(entorno):
    bus, container, conn = entorno

    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(RAFFLE_UUID))
    bus.publish(RAFFLE_BUDGET_RESERVED, _payload(RAFFLE_UUID))

    assert len(container.finance_service.asientos) == 1, (
        "La guardia gl: debe hacer idempotente el asiento ante redelivery."
    )


@pytest.mark.parametrize("evento", RAFFLE_EVENTS)
def test_all_raffle_channels_post(entorno, evento):
    bus, container, _conn = entorno
    bus.publish(evento, _payload("0198c0de-1234-7abc-8def-00000000000f"))
    assert len(container.finance_service.asientos) == 1


def test_empty_raffle_id_does_not_post(entorno):
    bus, container, _conn = entorno
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
