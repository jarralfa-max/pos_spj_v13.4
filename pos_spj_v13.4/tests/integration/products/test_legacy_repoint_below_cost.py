"""PROD corte de legacy (repoint batch 7) — alerta de venta bajo costo.

`ProcesarVentaUC.validar_precios_bajo_costo` leía el costo del producto de la
tabla legacy `productos.precio_compra`. Ahora lo toma del costo canónico
`product_cost.average_cost` (sucursal global `''`), poblado por el backfill 150.
"""

import sqlite3
import types

from backend.shared.ids import new_uuid


def _uc_with_cost(product_id, average_cost):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE product_cost (id TEXT PRIMARY KEY, product_id TEXT, "
                 "branch_id TEXT, average_cost TEXT)")
    if average_cost is not None:
        conn.execute("INSERT INTO product_cost VALUES (?,?,?,?)",
                     (new_uuid(), product_id, "", average_cost))
    conn.commit()
    from core.use_cases.venta import ProcesarVentaUC
    uc = ProcesarVentaUC.__new__(ProcesarVentaUC)
    uc._sales = types.SimpleNamespace(db=conn)
    return uc


def _item(product_id, nombre, precio_unit):
    return types.SimpleNamespace(producto_id=product_id, nombre=nombre,
                                 precio_unit=precio_unit)


def test_alerta_cuando_precio_bajo_costo_canonico():
    uc = _uc_with_cost("p1", "50.0")
    alertas = uc.validar_precios_bajo_costo([_item("p1", "Pollo", 40.0)])
    assert len(alertas) == 1
    assert alertas[0]["costo"] == 50.0 and alertas[0]["precio_venta"] == 40.0


def test_sin_alerta_cuando_precio_sobre_costo():
    uc = _uc_with_cost("p1", "50.0")
    assert uc.validar_precios_bajo_costo([_item("p1", "Pollo", 60.0)]) == []


def test_sin_costo_canonico_no_alerta():
    uc = _uc_with_cost("p1", None)  # sin fila en product_cost → costo 0 → sin alerta
    assert uc.validar_precios_bajo_costo([_item("p1", "Pollo", 10.0)]) == []
