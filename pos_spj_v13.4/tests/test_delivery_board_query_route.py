"""Canonical Delivery board read route — DeliveryQueryService → DTO.

Verifies the single read route used by the Kanban + list board:
- orders appear even when `drivers`/`ventas` tables are absent
- orders appear across divergent schemas (missing `fecha_solicitud`)
- legacy Spanish status maps to canonical enum without dropping rows
- the acceptance metric holds: repository rows == query DTOs (filter=Todos)

No PyQt import — exercises the application/query layer headlessly.
"""
from __future__ import annotations

import sqlite3

import pytest

from core.delivery.application.query_service import DeliveryQueryService
from core.delivery.domain.value_objects import DeliveryStatus, FulfillmentType


def _conn(script: str) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(script)
    return conn


# Migrator-style schema (has fecha/fecha_actualizacion/source_channel, NO fecha_solicitud,
# and crucially NO drivers/ventas tables).
_MIGRATOR_SCHEMA = """
CREATE TABLE delivery_orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, folio TEXT,
  cliente_nombre TEXT, cliente_tel TEXT, direccion TEXT NOT NULL DEFAULT 'Sin dirección',
  estado TEXT DEFAULT 'pendiente', total REAL DEFAULT 0, driver_id INTEGER,
  sucursal_id INTEGER DEFAULT 1, workflow_type TEXT, delivery_type TEXT,
  scheduled_at DATETIME, source_channel TEXT DEFAULT 'whatsapp',
  adjustment_pending INTEGER DEFAULT 0, fecha DATETIME, fecha_actualizacion DATETIME,
  pago_metodo TEXT, pago_monto REAL
);
"""

# Base m000-style schema (has fecha_solicitud, NO folio/total/workflow_type/source_channel).
_BASE_SCHEMA = """
CREATE TABLE delivery_orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, venta_id INTEGER, driver_id INTEGER,
  cliente_id INTEGER, direccion TEXT, estado TEXT DEFAULT 'pendiente', notas TEXT,
  cliente_nombre TEXT, cliente_tel TEXT, fecha_solicitud DATETIME, sucursal_id INTEGER DEFAULT 1
);
"""


def test_orders_visible_without_drivers_or_ventas_tables():
    conn = _conn(_MIGRATOR_SCHEMA)
    conn.execute(
        "INSERT INTO delivery_orders(folio,estado,cliente_nombre,total,fecha) "
        "VALUES('DEL-1','pendiente','Juan',150.0,'2026-06-20')"
    )
    dtos = DeliveryQueryService(conn).list_orders(branch_id=None)
    assert len(dtos) == 1
    assert dtos[0].status is DeliveryStatus.PENDING
    assert dtos[0].customer_name == "Juan"
    assert dtos[0].direccion  # carried through


def test_orders_visible_on_base_schema_without_fecha_solicitud_missing_cols():
    conn = _conn(_BASE_SCHEMA)
    conn.execute(
        "INSERT INTO delivery_orders(estado,cliente_nombre,fecha_solicitud) "
        "VALUES('preparacion','Ana','2026-06-19')"
    )
    dtos = DeliveryQueryService(conn).list_orders(branch_id=None)
    assert len(dtos) == 1
    assert dtos[0].status is DeliveryStatus.PREPARING
    # Columns absent in this schema fall back to defaults, never raise.
    assert dtos[0].total == 0
    assert dtos[0].workflow_type == ""


def test_acceptance_metric_all_rows_become_dtos():
    conn = _conn(_MIGRATOR_SCHEMA)
    statuses = ["pendiente", "preparacion", "en_ruta", "entregado", "cancelado"]
    for i, st in enumerate(statuses):
        conn.execute(
            "INSERT INTO delivery_orders(folio,estado,cliente_nombre,total,fecha) "
            "VALUES(?,?,?,?,?)",
            (f"DEL-{i}", st, f"C{i}", 10.0 * i, "2026-06-20"),
        )
    n = conn.execute("SELECT COUNT(*) FROM delivery_orders").fetchone()[0]
    dtos = DeliveryQueryService(conn).list_orders(branch_id=None)
    assert n == len(statuses)
    assert len(dtos) == n  # zero rows dropped silently


def test_legacy_status_maps_to_canonical_enum():
    conn = _conn(_MIGRATOR_SCHEMA)
    conn.execute(
        "INSERT INTO delivery_orders(folio,estado,cliente_nombre,fecha) "
        "VALUES('DEL-x','en_ruta','Z','2026-06-20')"
    )
    dto = DeliveryQueryService(conn).list_orders(branch_id=None)[0]
    assert dto.status is DeliveryStatus.IN_TRANSIT
    assert dto.status_legacy == "en_ruta"  # legacy preserved for board filters


def test_fulfillment_type_mapping_pickup_vs_delivery():
    conn = _conn(_MIGRATOR_SCHEMA)
    conn.execute(
        "INSERT INTO delivery_orders(folio,estado,delivery_type,fecha) "
        "VALUES('DEL-p','pendiente','pickup','2026-06-20')"
    )
    conn.execute(
        "INSERT INTO delivery_orders(folio,estado,delivery_type,fecha) "
        "VALUES('DEL-d','pendiente','domicilio','2026-06-20')"
    )
    dtos = DeliveryQueryService(conn).list_orders(branch_id=None)
    by_folio = {d.folio: d for d in dtos}
    assert by_folio["DEL-p"].fulfillment_type is FulfillmentType.PICKUP
    assert by_folio["DEL-d"].fulfillment_type is FulfillmentType.DELIVERY


def test_empty_db_returns_empty_without_error():
    conn = _conn(_MIGRATOR_SCHEMA)
    assert DeliveryQueryService(conn).list_orders(branch_id=None) == []


def test_status_filter_applies_after_enum_mapping():
    conn = _conn(_MIGRATOR_SCHEMA)
    for st in ("pendiente", "entregado"):
        conn.execute(
            "INSERT INTO delivery_orders(folio,estado,fecha) VALUES(?,?,?)",
            (f"DEL-{st}", st, "2026-06-20"),
        )
    svc = DeliveryQueryService(conn)
    only_pending = svc.list_orders(branch_id=None, status=DeliveryStatus.PENDING)
    assert len(only_pending) == 1
    assert only_pending[0].status is DeliveryStatus.PENDING


# ── End-to-end: DTO → canonical mapper → board filters/columns ──────────────

def test_mapper_and_filters_preserve_all_orders_end_to_end():
    """Acceptance metric: N rows → N DTOs → N view rows → all placed in a column."""
    from core.utils.delivery_ui_filters import dto_to_view, matches_operational_tab
    from core.delivery.application.kanban_config import KANBAN_COLUMNS
    from core.delivery.domain.value_objects import LEGACY_STATUS_MAP

    # Reproduce the UI's _STATUS_TO_COL build.
    status_to_col: dict[str, int] = {}
    for col_idx, (_title, statuses) in enumerate(KANBAN_COLUMNS):
        for ds in statuses:
            for legacy, canonical in LEGACY_STATUS_MAP.items():
                if canonical == ds:
                    status_to_col[legacy] = col_idx
            status_to_col[ds.value] = col_idx

    conn = _conn(_MIGRATOR_SCHEMA)
    statuses = ["pendiente", "preparacion", "en_ruta", "entregado"]
    for i, st in enumerate(statuses):
        conn.execute(
            "INSERT INTO delivery_orders(folio,estado,cliente_nombre,total,fecha) "
            "VALUES(?,?,?,?,?)",
            (f"DEL-{i}", st, f"C{i}", 10.0, "2026-06-20"),
        )
    dtos = DeliveryQueryService(conn).list_orders(branch_id=None)
    views = [dto_to_view(d) for d in dtos]
    assert len(views) == len(statuses)
    # Filtro "Todos" → every order matches the operational tab.
    assert all(matches_operational_tab(v, None) for v in views)
    # Every order lands in exactly one Kanban column (none silently dropped).
    placed = [v for v in views if status_to_col.get(v["estado"]) is not None]
    assert len(placed) == len(statuses)


def test_count_orders_matches_list_len_and_survives_missing_tables():
    conn = _conn(_MIGRATOR_SCHEMA)
    for i in range(3):
        conn.execute(
            "INSERT INTO delivery_orders(folio,estado,fecha) VALUES(?,?,?)",
            (f"DEL-{i}", "pendiente", "2026-06-20"),
        )
    svc = DeliveryQueryService(conn)
    assert svc.count_orders(branch_id=None) == 3
    assert svc.count_orders(branch_id=None) == len(svc.list_orders(branch_id=None))
