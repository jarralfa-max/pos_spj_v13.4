# tests/unit/test_remediacion0_cxc_cxp_events.py
"""Remediación 0 — B10: crear CxC/CxP debe publicar CXC_CREADA/CXP_CREADA.

Bug original: la UI de Finanzas (finanzas_unificadas) está suscrita a los
canales CXC_CREADA/CXP_CREADA, pero ningún servicio los publicaba — el string
`evento=` de registrar_asiento() es solo metadata del asiento, no un publish.
Resultado: las pestañas CxC/CxP nunca se refrescaban al crear cuentas.
"""
from __future__ import annotations

import re
import sqlite3

import pytest

from core.events.event_bus import EventBus
from core.events.domain_events import (
    ACCOUNT_RECEIVABLE_CREATED,  # "CXC_CREADA"
    ACCOUNT_PAYABLE_CREATED,     # "CXP_CREADA"
)

UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)


@pytest.fixture()
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE accounts_receivable (
            id TEXT PRIMARY KEY, folio TEXT, cliente_id TEXT, venta_id TEXT,
            concepto TEXT, amount REAL, balance REAL, due_date TEXT,
            status TEXT, tipo TEXT, usuario TEXT,
            updated_at TEXT
        );
        CREATE TABLE accounts_payable (
            id TEXT PRIMARY KEY, folio TEXT, supplier_id TEXT, concepto TEXT,
            amount REAL, balance REAL, due_date TEXT, status TEXT, tipo TEXT,
            referencia TEXT, ref_type TEXT, usuario TEXT, notas TEXT,
            updated_at TEXT
        );
        """
    )
    yield conn
    conn.close()


@pytest.fixture()
def captura_bus():
    bus = EventBus()
    recibidos = []

    def _capture(payload):
        recibidos.append(payload)

    for canal in (ACCOUNT_RECEIVABLE_CREATED, ACCOUNT_PAYABLE_CREATED):
        bus.clear_handlers(canal)
    bus.subscribe(ACCOUNT_RECEIVABLE_CREATED, _capture, label="test.cxc")
    bus.subscribe(ACCOUNT_PAYABLE_CREATED, _capture, label="test.cxp")
    yield recibidos
    for canal in (ACCOUNT_RECEIVABLE_CREATED, ACCOUNT_PAYABLE_CREATED):
        bus.clear_handlers(canal)


def test_crear_cxc_publica_evento(db, captura_bus):
    from core.services.finance.accounts_receivable_service import AccountsReceivableService

    svc = AccountsReceivableService(db, ledger_service=None)
    ar_id = svc.crear_cxc(
        cliente_id="0198c0de-cccc-7ddd-8eee-000000000001",
        concepto="Venta a crédito test",
        amount=250.0,
        usuario="tester",
    )

    assert len(captura_bus) == 1, "crear_cxc no publicó CXC_CREADA al bus"
    evt = captura_bus[0]
    assert evt["entity_id"] == str(ar_id)
    assert evt["monto"] == 250.0
    assert evt["source_module"] == "accounts_receivable_service"
    # event_id y operation_id son UUIDv7 independientes (contrato EVENT_CATALOG)
    assert UUID_RE.match(evt["event_id"])
    assert UUID_RE.match(evt["operation_id"])
    assert evt["event_id"] != evt["operation_id"]


def test_crear_cxp_publica_evento(db, captura_bus):
    from core.services.finance.accounts_payable_service import AccountsPayableService

    svc = AccountsPayableService(db, ledger_service=None)
    ap_id = svc.crear_cxp(
        supplier_id="0198c0de-ffff-7aaa-8bbb-000000000002",
        concepto="Factura proveedor test",
        amount=990.0,
        usuario="tester",
    )

    assert len(captura_bus) == 1, "crear_cxp no publicó CXP_CREADA al bus"
    evt = captura_bus[0]
    assert evt["entity_id"] == str(ap_id)
    assert evt["monto"] == 990.0
    assert evt["source_module"] == "accounts_payable_service"
    assert UUID_RE.match(evt["event_id"])
    assert UUID_RE.match(evt["operation_id"])


def test_fila_persistida_coincide_con_evento(db, captura_bus):
    from core.services.finance.accounts_receivable_service import AccountsReceivableService

    svc = AccountsReceivableService(db, ledger_service=None)
    ar_id = svc.crear_cxc(cliente_id=None, concepto="x", amount=10.0)

    row = db.execute(
        "SELECT id, balance FROM accounts_receivable WHERE id=?", (ar_id,)
    ).fetchone()
    assert row is not None and row["balance"] == 10.0
    assert captura_bus and captura_bus[0]["entity_id"] == row["id"]
