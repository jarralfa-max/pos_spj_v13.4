from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest


def _products_module():
    try:
        from modulos.productos import DialogoProducto
    except ImportError as exc:
        pytest.skip(f"PyQt products module unavailable in this environment: {exc}")
    return DialogoProducto


def _app():
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError as exc:
        pytest.skip(f"PyQt unavailable in this environment: {exc}")
    return QApplication.instance() or QApplication([])


def _container() -> SimpleNamespace:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            codigo TEXT,
            codigo_barras TEXT,
            categoria TEXT,
            precio REAL DEFAULT 0,
            precio_compra REAL DEFAULT 0,
            precio_minimo_venta REAL DEFAULT 0,
            costo REAL DEFAULT 0,
            unidad TEXT DEFAULT 'pza',
            unidad_venta TEXT DEFAULT 'pza',
            unidad_compra TEXT DEFAULT 'pza',
            stock_minimo REAL DEFAULT 0,
            tipo_producto TEXT DEFAULT 'simple',
            es_compuesto INTEGER DEFAULT 0,
            es_subproducto INTEGER DEFAULT 0,
            imagen_path TEXT,
            existencia REAL DEFAULT 0,
            oculto INTEGER DEFAULT 0,
            activo INTEGER DEFAULT 1,
            ultima_actualizacion TEXT
        )
        """
    )
    return SimpleNamespace(db=conn)


def test_product_dialog_dependencies_are_initialized_before_ui() -> None:
    _app()
    DialogoProducto = _products_module()

    dialog = DialogoProducto(_container())

    assert dialog.product_query_service is not None
    assert dialog.create_product_use_case is not None
    assert dialog.update_product_use_case is not None
