"""El rastro de auditoría de los contextos acotados, contra la tabla real.

Cubre lo que reemplazó a `core.services.auto_audit.audit_write`. Los cuatro
contextos que auditan (Ventas, Fidelidad, Tarjetas, Reparto) escriben en la
MISMA tabla `audit_logs`: una auditoría repartida en cinco tablas no se puede
leer en orden cronológico, que es justo para lo que sirve.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

import pytest

from backend.application.loyalty.audit import record_loyalty_audit_entry
from backend.application.loyalty_cards.audit import record_card_audit_entry
from backend.application.orders_delivery.audit import record_orders_delivery_audit_entry
from backend.application.sales.audit import record_sales_audit_entry
from backend.application.shared.audit_trail import record_audit_entry
from backend.infrastructure.db.repositories.settings.audit_log_repository import (
    SqliteAuditLogRepository,
)
from backend.shared.ids import new_uuid


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute(
        """
        CREATE TABLE audit_logs (
            id TEXT NOT NULL PRIMARY KEY,
            accion TEXT NOT NULL, modulo TEXT NOT NULL,
            entidad TEXT, entidad_id TEXT,
            usuario TEXT NOT NULL DEFAULT 'Sistema',
            sucursal_id TEXT, valor_antes TEXT, valor_despues TEXT,
            detalles TEXT, ip TEXT,
            fecha DATETIME DEFAULT (datetime('now'))
        )
        """
    )
    c.commit()
    yield c
    c.close()


@dataclass
class _Entry:
    """Objeto de valor genérico con la forma que comparten los cuatro."""

    action: str = "cancelar"
    user_id: str = "cajero-1"
    branch_id: str | None = None
    operation_id: str = ""
    authorized_by: str | None = None
    reason: str | None = None
    device_id: str | None = None
    occurred_at: str | None = None
    before: dict = field(default_factory=dict)
    after: dict = field(default_factory=dict)
    entity_id: str = ""
    sale_id: str = ""
    card_id: str = ""


def _rows(conn) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM audit_logs ORDER BY rowid").fetchall()


# ── el sumidero compartido ──────────────────────────────────────────────────
def test_an_entry_lands_with_its_module_and_entity(conn):
    record_audit_entry(conn, _Entry(action="anular"), module="POS", entity="venta",
                       entity_id="V-1")
    fila = _rows(conn)[0]
    assert (fila["modulo"], fila["entidad"], fila["entidad_id"], fila["accion"]) == (
        "POS", "venta", "V-1", "anular")


def test_the_extra_fields_travel_inside_details(conn):
    """`audit_logs` no tiene columna para ellos, y perderlos dejaría la
    anotación sin con qué enlazarla al resto de la operación."""
    operation_id = new_uuid()
    record_audit_entry(
        conn, _Entry(operation_id=operation_id, authorized_by="gerente",
                     reason="producto dañado", device_id="caja-2"),
        module="POS", entity="venta", entity_id="V-1")

    detalles = json.loads(_rows(conn)[0]["detalles"])
    assert detalles["operation_id"] == operation_id
    assert detalles["authorized_by"] == "gerente"
    assert detalles["reason"] == "producto dañado"
    assert detalles["device_id"] == "caja-2"


def test_absent_extras_are_omitted_not_stored_as_null_text(conn):
    """Un `"authorized_by": null` en el JSON se lee como "se intentó y no
    había"; omitirlo dice lo que de verdad pasó: no aplica."""
    record_audit_entry(conn, _Entry(), module="POS", entity="venta", entity_id="V-1")
    detalles = json.loads(_rows(conn)[0]["detalles"])
    assert "authorized_by" not in detalles
    assert "reason" not in detalles


def test_before_and_after_are_stored_as_json(conn):
    record_audit_entry(
        conn, _Entry(before={"estado": "abierta"}, after={"estado": "cancelada"}),
        module="POS", entity="venta", entity_id="V-1")
    fila = _rows(conn)[0]
    assert json.loads(fila["valor_antes"]) == {"estado": "abierta"}
    assert json.loads(fila["valor_despues"]) == {"estado": "cancelada"}


def test_an_operation_without_an_actor_is_still_attributable(conn):
    """`usuario` es NOT NULL; una anotación sin autor es peor que inútil."""
    record_audit_entry(conn, _Entry(user_id=""), module="POS", entity="venta",
                       entity_id="V-1")
    assert _rows(conn)[0]["usuario"] == "Sistema"


def test_the_branch_is_recorded_when_there_is_one(conn):
    branch_id = new_uuid()
    record_audit_entry(conn, _Entry(branch_id=branch_id), module="POS",
                       entity="venta", entity_id="V-1")
    assert _rows(conn)[0]["sucursal_id"] == branch_id


def test_an_entry_missing_optional_attributes_does_not_break(conn):
    """Los cuatro objetos de valor NO comparten un tipo base: cada contexto
    define el suyo, y no todos traen los mismos campos."""

    class _Minima:
        action = "crear"
        user_id = "u1"

    record_audit_entry(conn, _Minima(), module="DELIVERY", entity="pedido_delivery",
                       entity_id="P-1")
    assert _rows(conn)[0]["accion"] == "crear"


# ── los cuatro contextos ────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "writer, kwargs, modulo, entidad",
    [
        (record_sales_audit_entry, {"sale_id": "V-9"}, "POS", "venta"),
        (record_loyalty_audit_entry, {"entity_id": "F-9"}, "GROWTH_ENGINE", "fidelidad"),
        (record_card_audit_entry, {"card_id": "T-9"}, "TARJETAS_FIDELIDAD",
         "tarjeta_fidelidad"),
        (record_orders_delivery_audit_entry, {"entity_id": "P-9"}, "DELIVERY",
         "pedido_delivery"),
    ],
)
def test_each_context_writes_under_its_own_module(conn, writer, kwargs, modulo, entidad):
    writer(conn, _Entry(**kwargs))
    fila = _rows(conn)[0]
    assert (fila["modulo"], fila["entidad"]) == (modulo, entidad)
    assert fila["entidad_id"] == next(iter(kwargs.values()))


def test_all_four_contexts_share_one_readable_trail(conn):
    """Lo que se pierde con una tabla por contexto: el orden cronológico."""
    record_sales_audit_entry(conn, _Entry(sale_id="V-1"))
    record_loyalty_audit_entry(conn, _Entry(entity_id="F-1"))
    record_card_audit_entry(conn, _Entry(card_id="T-1"))
    record_orders_delivery_audit_entry(conn, _Entry(entity_id="P-1"))
    conn.commit()

    modulos = [fila[2] for fila in SqliteAuditLogRepository(conn).recent(limit=10)]
    assert set(modulos) == {"POS", "GROWTH_ENGINE", "TARJETAS_FIDELIDAD", "DELIVERY"}


def test_the_writers_take_a_connection_not_a_container(conn):
    """La razón por la que esto nunca se usó.

    `audit_write()` pedía un `container` que los casos de uso no tienen —
    documentado como limitación abierta en `sales/use_cases/_base.py`. Que la
    firma acepte la `connection` es lo que lo desbloquea, así que se fija.
    """
    import inspect

    for writer in (record_sales_audit_entry, record_loyalty_audit_entry,
                   record_card_audit_entry, record_orders_delivery_audit_entry):
        primero = list(inspect.signature(writer).parameters)[0]
        assert primero == "connection", f"{writer.__name__} recibe {primero!r}"
