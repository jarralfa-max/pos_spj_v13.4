# tests/unit/test_remediacion_b_refresh_contract.py
"""Remediación B — contrato de refresh en caliente (DEEP_AUDIT §13, B-V1, B16).

El fan-out de MainWindow (core/events/catalog_events.py) propaga
PRODUCTS_CHANGED / BRANCHES_CHANGED llamando, por widget, a
on_products_changed/refresh_products (o on_branches_changed/refresh_branches).

Estos tests verifican, SIN PyQt real, que:
  1. fan_out_products_changed / fan_out_branches_changed invocan el contrato en
     widgets fake que lo implementan (como Ventas/Transferencias/Delivery ahora).
  2. Los módulos objetivo declaran los métodos del contrato (guardrail AST).
"""
from __future__ import annotations
import pytest

import ast
from pathlib import Path

from core.events.catalog_events import (
    fan_out_products_changed,
    fan_out_branches_changed,
)

PKG_ROOT = Path(__file__).resolve().parents[2]


class _FakeVentas:
    """Simula el contrato implementado en Ventas/Delivery."""
    def __init__(self):
        self.calls = []

    def on_products_changed(self, payload):
        self.calls.append(("products", payload))

    def on_branches_changed(self, payload):
        self.calls.append(("branches", payload))


class _FakeRefreshOnly:
    """Widget que solo expone refresh_* (segunda preferencia del fan-out)."""
    def __init__(self):
        self.calls = []

    def refresh_products(self):
        self.calls.append("refresh_products")

    def refresh_branches(self):
        self.calls.append("refresh_branches")


def test_fan_out_products_llama_on_products_changed():
    w = _FakeVentas()
    notified = fan_out_products_changed([w], {"product_id": "P1", "action": "created"})
    assert w in notified
    assert w.calls == [("products", {"product_id": "P1", "action": "created"})]


def test_fan_out_branches_llama_on_branches_changed():
    w = _FakeVentas()
    notified = fan_out_branches_changed([w], {"branch_id": "B1", "action": "created"})
    assert w in notified
    assert w.calls == [("branches", {"branch_id": "B1", "action": "created"})]


def test_fan_out_usa_refresh_como_segunda_preferencia():
    w = _FakeRefreshOnly()
    fan_out_products_changed([w], {"product_id": "P1"})
    fan_out_branches_changed([w], {"branch_id": "B1"})
    assert w.calls == ["refresh_products", "refresh_branches"]


def test_fan_out_aisla_errores_por_widget():
    class _Boom:
        def on_products_changed(self, payload):
            raise RuntimeError("boom")
    ok = _FakeVentas()
    boom = _Boom()
    # El error de un widget no impide notificar a los demás.
    notified = fan_out_products_changed([boom, ok], {"x": 1})
    assert ok in notified


# ── Guardrails AST: los módulos objetivo declaran el contrato ────────────────

def _class_methods(rel_path: str) -> set[str]:
    src = (PKG_ROOT / rel_path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    methods: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            methods.add(node.name)
    return methods


def test_ventas_declara_contrato_productos():
    m = _class_methods("modulos/ventas.py")
    assert {"refresh_products", "on_products_changed"} <= m, (
        "B-V1: Ventas debe implementar el contrato de refresh de productos."
    )


def test_transferencias_declara_contrato_sucursales_y_productos():
    m = _class_methods("modulos/transferencias.py")
    assert {"refresh_branches", "on_branches_changed",
            "refresh_products", "on_products_changed"} <= m, (
        "Transferencias debe reaccionar a BRANCHES_CHANGED/PRODUCTS_CHANGED."
    )


def test_delivery_declara_contrato():
    m = _class_methods("modulos/delivery.py")
    assert {"refresh_products", "on_products_changed"} <= m


def test_inventario_escucha_inventario_actualizado():
    pytest.skip("INV-27: inventario_local eliminado; refresh en vivo no portado a la UI enterprise de solo lectura")
    src = (PKG_ROOT / "modulos" / "inventario_local.py").read_text(encoding="utf-8")
    # El _init_refresh debe incluir el canal canónico de stock.
    assert '"INVENTARIO_ACTUALIZADO"' in src, (
        "B16: Inventario debe escuchar INVENTARIO_ACTUALIZADO (evento canónico "
        "de todos los escritores de stock)."
    )
