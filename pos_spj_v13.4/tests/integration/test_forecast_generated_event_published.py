"""FORECAST_GENERADO se publica al EventBus con IDs UUID string."""
from __future__ import annotations

import core.services.forecast_service as fs_module
from backend.shared.ids import new_uuid
from tests.integration._born_clean_db import make_db


class _FakeSeries(list):
    def apply(self, fn):
        return _FakeSeries(fn(x) for x in self)

    def sum(self):
        return float(sum(self))

    def tolist(self):
        return list(self)


class _FakeFit:
    def __init__(self, values):
        self._values = values

    def forecast(self, steps):
        return _FakeSeries([10.0] * steps)


class _FakeES:
    def __init__(self, series, **kwargs):
        self._series = series

    def fit(self):
        return _FakeFit(self._series)


class _FakeIndex(list):
    @property
    def min(self):
        return lambda: self[0]

    @property
    def max(self):
        return lambda: self[-1]


class _FakeDF:
    """DataFrame mínimo para el flujo de generar_plan_compras."""

    def __init__(self, rows):
        import datetime as _dt

        self._rows = rows
        self.empty = not rows
        self.index = _FakeIndex([_dt.datetime(2026, 7, d + 1) for d in range(len(rows))])

    def __len__(self):
        return len(self._rows)

    def set_index(self, col, inplace=False):
        return self

    def reindex(self, idx, fill_value=0.0):
        self.index = _FakeIndex(list(idx))
        return self

    def __getitem__(self, key):
        return _FakeSeries(r[1] for r in self._rows)


class _FakePandas:
    def read_sql_query(self, sql, conn, params=(), parse_dates=None):
        rows = conn.execute(sql, params).fetchall()
        return _FakeDF([tuple(r) for r in rows])

    def date_range(self, start, end, freq="D"):
        import datetime as _dt

        days = (end - start).days
        return [start + _dt.timedelta(days=i) for i in range(days + 1)]


def test_forecast_publishes_event_with_uuid_ids(monkeypatch):
    conn = make_db()
    producto_id, sucursal_id = new_uuid(), new_uuid()
    conn.execute(
        "INSERT INTO productos (id, nombre, activo, existencia) VALUES (?, 'P', 1, 20)",
        (producto_id,),
    )
    for i, qty in enumerate((5, 8, 6, 9)):
        venta_id = new_uuid()
        conn.execute(
            "INSERT INTO ventas (id, folio, sucursal_id, total, estado, fecha) "
            f"VALUES (?, 'F-{i}', ?, 100, 'completada', date('now','-{i+1} days'))",
            (venta_id, sucursal_id),
        )
        conn.execute(
            "INSERT INTO detalles_venta (id, venta_id, producto_id, cantidad, "
            " precio_unitario, subtotal) VALUES (?, ?, ?, ?, 10, ?)",
            (new_uuid(), venta_id, producto_id, qty, qty * 10),
        )

    monkeypatch.setattr(fs_module, "pd", _FakePandas())
    monkeypatch.setattr(fs_module, "ExponentialSmoothing", _FakeES)

    published = []

    class _Bus:
        def publish(self, evento, payload, **kwargs):
            published.append((evento, payload))

    svc = fs_module.ForecastService(conn)
    svc._bus = _Bus()

    resultado = svc.generar_plan_compras(producto_id, sucursal_id, 30, 7, 5.0)

    assert resultado["metricas"]["stock_actual"] == 20
    assert resultado["metricas"]["venta_proyectada"] == 70.0
    assert resultado["metricas"]["compra_recomendada"] == 55.0
    assert resultado["pronostico_valores"] == [10.0] * 7

    assert len(published) == 1
    _, payload = published[0]
    assert payload["producto_id"] == producto_id
    assert payload["sucursal_id"] == sucursal_id
    assert isinstance(payload["producto_id"], str)
    assert payload["compra_recomendada"] == 55.0
