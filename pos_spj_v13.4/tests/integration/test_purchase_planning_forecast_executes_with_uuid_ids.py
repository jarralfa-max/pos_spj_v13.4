"""El forecast de planeación ejecuta con producto_id/sucursal_id UUID string."""
from __future__ import annotations

import inspect

import pytest

import core.services.forecast_service as fs_module
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db
from tests.integration.test_forecast_generated_event_published import (
    _FakeES,
    _FakePandas,
)


def test_signature_declares_str_ids():
    sig = inspect.signature(fs_module.ForecastService.generar_plan_compras)
    assert sig.parameters["producto_id"].annotation in (str, "str")
    assert sig.parameters["sucursal_id"].annotation in (str, "str")


def test_forecast_executes_with_uuid_ids(monkeypatch):
    conn = make_db()
    producto_id, sucursal_id = new_uuid(), new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo, existencia) VALUES (?, 'P', 1, 4)",
        (producto_id,),
    )
    for i, qty in enumerate((3, 4, 5)):
        venta_id = new_uuid()
        conn.execute(
            "INSERT INTO ventas (id, folio, sucursal_id, total, estado, fecha) "
            f"VALUES (?, 'V-{i}', ?, 50, 'completada', date('now','-{i+1} days'))",
            (venta_id, sucursal_id),
        )
        conn.execute(
            "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, "
            " precio_unitario, subtotal) VALUES (?, ?, ?, ?, 10, ?)",
            (new_uuid(), venta_id, producto_id, qty, qty * 10),
        )

    monkeypatch.setattr(fs_module, "pd", _FakePandas())
    monkeypatch.setattr(fs_module, "ExponentialSmoothing", _FakeES)
    svc = fs_module.ForecastService(conn)
    svc._bus = None

    resultado = svc.generar_plan_compras(producto_id, sucursal_id, 30, 5, 2.0)
    assert resultado["metricas"]["stock_actual"] == 4
    assert len(resultado["pronostico_fechas"]) == 5


def test_insufficient_history_gives_clear_error(monkeypatch):
    conn = make_db()
    producto_id, sucursal_id = new_uuid(), new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo) VALUES (?, 'P', 1)",
        (producto_id,),
    )
    monkeypatch.setattr(fs_module, "pd", _FakePandas())
    monkeypatch.setattr(fs_module, "ExponentialSmoothing", _FakeES)
    svc = fs_module.ForecastService(conn)
    with pytest.raises(ValueError, match="históricos"):
        svc.generar_plan_compras(producto_id, sucursal_id, 30, 5, 2.0)
