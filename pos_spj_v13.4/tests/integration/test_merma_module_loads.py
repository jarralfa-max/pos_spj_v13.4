from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest


def _connection() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE productos (
            id INTEGER PRIMARY KEY,
            nombre TEXT NOT NULL,
            precio_compra REAL,
            unidad TEXT,
            existencia REAL,
            activo INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE mermas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            sucursal_id INTEGER,
            cantidad REAL,
            unidad TEXT,
            motivo TEXT,
            costo_unitario REAL,
            valor_perdida REAL,
            notas TEXT,
            usuario TEXT,
            operation_id TEXT,
            created_at TEXT,
            fecha TEXT
        )
    """)
    conn.execute(
        "INSERT INTO productos(id, nombre, precio_compra, unidad, existencia, activo) VALUES (1, 'Arrachera', 120, 'kg', 5, 1)"
    )
    conn.commit()
    return conn


def test_merma_module_loads_and_product_selection_uses_existing_tokens() -> None:
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - environment dependent Qt libraries
        pytest.skip(f"PyQt5 widgets unavailable: {exc}")

    from frontend.desktop.components.search_selector import SearchOption
    from modulos.merma import ModuloMerma

    app = QApplication.instance() or QApplication([])
    container = SimpleNamespace(db=_connection(), sucursal_id=1)
    widget = ModuloMerma(container)

    options = widget._buscar_productos("arra")
    assert options
    widget._on_producto_selected(SearchOption(id=options[0].id, label=options[0].label, subtitle=options[0].subtitle))
    widget.spin_cantidad.setValue(0.00)
    widget._actualizar_valor_perdida()

    assert widget.lbl_valor_perdida.text() == "$0.00"
    widget.deleteLater()
    app.processEvents()
