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
    conn.execute("""
        CREATE TABLE movimientos_inventario (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            producto_id INTEGER,
            tipo TEXT,
            tipo_movimiento TEXT,
            cantidad REAL,
            existencia_anterior REAL,
            existencia_nueva REAL,
            costo_unitario REAL,
            costo_total REAL,
            operation_id TEXT,
            sucursal_id TEXT,
            fecha TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE financial_event_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            evento TEXT,
            modulo TEXT,
            referencia_id TEXT,
            monto REAL,
            cuenta_debe TEXT,
            cuenta_haber TEXT,
            usuario_id TEXT,
            sucursal_id TEXT,
            metadata TEXT,
            timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute(
        "INSERT INTO productos(id, nombre, precio_compra, unidad, existencia, activo) VALUES (1, 'Arrachera', 120, 'kg', 5, 1)"
    )
    conn.commit()
    return conn


def _qt_merma_widget():
    try:
        from PyQt5.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - environment dependent Qt libraries
        pytest.skip(f"PyQt5 widgets unavailable: {exc}")

    from core.services.finance.general_ledger_service import GeneralLedgerService
    from modulos.merma import ModuloMerma

    app = QApplication.instance() or QApplication([])
    db = _connection()
    container = SimpleNamespace(db=db, sucursal_id=1, finance_service=GeneralLedgerService(db))
    widget = ModuloMerma(container)
    return app, widget


def test_merma_module_loads_and_product_selection_uses_existing_tokens() -> None:
    app, widget = _qt_merma_widget()

    from modulos.merma import SearchOption

    options = widget._buscar_productos("arra")
    assert options
    widget._on_producto_selected(SearchOption(id=options[0].id, label=options[0].label, subtitle=options[0].subtitle))
    widget.spin_cantidad.setValue(2.00)
    widget._actualizar_valor_perdida()

    assert widget._selected_product["id"] == 1
    assert widget._selected_product["name"] == "Arrachera"
    assert widget.spin_cantidad.suffix() == " kg"
    assert "Stock actual: 5.00 kg" in widget.lbl_producto_info.text()
    assert "Costo: $120.00/kg" in widget.lbl_producto_info.text()
    assert widget.lbl_valor_perdida.text() == "$240.00"
    widget.deleteLater()
    app.processEvents()


def test_merma_register_without_product_warns_without_crashing(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    warnings = []

    from PyQt5.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, title, message, *args: warnings.append((title, message)))

    widget._registrar()

    assert warnings == [("Aviso", "Selecciona un producto.")]
    widget.deleteLater()
    app.processEvents()


def test_merma_register_zero_quantity_warns_without_crashing(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    warnings = []

    from PyQt5.QtWidgets import QMessageBox
    from modulos.merma import SearchOption

    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, title, message, *args: warnings.append((title, message)))

    option = widget._buscar_productos("arra")[0]
    widget._on_producto_selected(SearchOption(id=option.id, label=option.label, subtitle=option.subtitle))
    widget.spin_cantidad.setValue(0.00)
    widget._registrar()

    assert warnings == [("Aviso", "La cantidad debe ser > 0.")]
    widget.deleteLater()
    app.processEvents()


def test_merma_register_valid_waste_uses_selected_product_and_decreases_inventory(monkeypatch) -> None:
    app, widget = _qt_merma_widget()

    from modulos.merma import SearchOption
    import core.permissions as permissions
    import modulos.merma as merma_module

    monkeypatch.setattr(permissions, "verificar_permiso", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(merma_module.Toast, "success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(widget, "_registrar_auditoria", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(widget, "_cargar_historial", lambda: None)

    option = widget._buscar_productos("arra")[0]
    widget._on_producto_selected(SearchOption(id=option.id, label=option.label, subtitle=option.subtitle))
    widget.spin_cantidad.setValue(2.00)
    widget.set_usuario_actual("tester")

    widget._registrar()

    row = widget.container.db.execute(
        "SELECT producto_id, cantidad, valor_perdida, usuario FROM mermas"
    ).fetchone()
    stock = widget.container.db.execute("SELECT existencia FROM productos WHERE id = 1").fetchone()[0]

    movement_row = widget.container.db.execute(
        "SELECT tipo, tipo_movimiento, cantidad, existencia_anterior, existencia_nueva FROM movimientos_inventario"
    ).fetchone()
    finance_row = widget.container.db.execute(
        "SELECT evento, monto FROM financial_event_log WHERE evento = 'WASTE_REGISTERED'"
    ).fetchone()

    assert row == (1, 2.0, 240.0, "tester")
    assert stock == 3.0
    assert movement_row == ("MERMA", "waste", 2.0, 5.0, 3.0)
    assert finance_row == ("WASTE_REGISTERED", 240.0)
    assert widget._selected_product is None
    widget.deleteLater()
    app.processEvents()


def test_merma_register_high_value_requests_pin_before_use_case(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    warnings = []
    pins = []

    from PyQt5.QtWidgets import QMessageBox, QInputDialog
    from modulos.merma import SearchOption
    import core.permissions as permissions
    import modulos.merma as merma_module
    from core.services.discount_guard import DiscountGuard

    monkeypatch.setattr(permissions, "verificar_permiso", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message, *args: warnings.append((title, message)) or QMessageBox.Yes,
    )
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args, **_kwargs: ("1234", True))
    monkeypatch.setattr(DiscountGuard, "solicitar_pin_gerente", lambda _self, _db, pin: pins.append(pin) or True)
    monkeypatch.setattr(merma_module.Toast, "success", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(widget, "_registrar_auditoria", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(widget, "_cargar_historial", lambda: None)

    option = widget._buscar_productos("arra")[0]
    widget._on_producto_selected(SearchOption(id=option.id, label=option.label, subtitle=option.subtitle))
    widget.spin_cantidad.setValue(5.00)
    widget.set_usuario_actual("tester")

    widget._registrar()

    row = widget.container.db.execute(
        "SELECT cantidad, costo_unitario, valor_perdida FROM mermas"
    ).fetchone()
    finance_row = widget.container.db.execute(
        "SELECT evento, monto FROM financial_event_log WHERE evento = 'WASTE_REGISTERED'"
    ).fetchone()

    assert any(title == "⚠️ Merma de alto valor" for title, _message in warnings)
    assert pins == ["1234"]
    assert row == (5.0, 120.0, 600.0)
    assert finance_row == ("WASTE_REGISTERED", 600.0)
    widget.deleteLater()
    app.processEvents()


def test_merma_register_invalid_selected_product_id_warns(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    warnings = []

    from PyQt5.QtWidgets import QMessageBox
    import core.permissions as permissions

    monkeypatch.setattr(permissions, "verificar_permiso", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(QMessageBox, "warning", lambda _parent, title, message, *args: warnings.append((title, message)))

    widget._selected_product = {"id": "", "name": "Producto inválido", "unit": "kg", "stock": 5, "unit_cost": 1}
    widget.spin_cantidad.setValue(1.00)
    widget._registrar()

    assert warnings == [("Aviso", "El producto seleccionado no tiene un ID válido.")]
    widget.deleteLater()
    app.processEvents()


def test_merma_register_use_case_failure_shows_critical(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    criticals = []

    from PyQt5.QtWidgets import QMessageBox
    from modulos.merma import SearchOption
    import core.permissions as permissions

    class FailingUseCase:
        def execute(self, _command):
            return SimpleNamespace(success=False, entity_id=None, message="WASTE_PRODUCT_NOT_FOUND")

    monkeypatch.setattr(permissions, "verificar_permiso", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, title, message, *args: criticals.append((title, message)))
    widget._register_waste_use_case = FailingUseCase()

    option = widget._buscar_productos("arra")[0]
    widget._on_producto_selected(SearchOption(id=option.id, label=option.label, subtitle=option.subtitle))
    widget.spin_cantidad.setValue(1.00)
    widget._registrar()

    assert criticals == [("Error", "WASTE_PRODUCT_NOT_FOUND")]
    assert widget.container.db.execute("SELECT COUNT(*) FROM mermas").fetchone()[0] == 0
    widget.deleteLater()
    app.processEvents()


def test_merma_register_execute_exception_is_reported(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    criticals = []

    from PyQt5.QtWidgets import QMessageBox
    from modulos.merma import SearchOption
    import core.permissions as permissions

    class ExplodingUseCase:
        def execute(self, _command):
            raise RuntimeError("db down")

    monkeypatch.setattr(permissions, "verificar_permiso", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, title, message, *args: criticals.append((title, message)))
    widget._register_waste_use_case = ExplodingUseCase()

    option = widget._buscar_productos("arra")[0]
    widget._on_producto_selected(SearchOption(id=option.id, label=option.label, subtitle=option.subtitle))
    widget.spin_cantidad.setValue(1.00)
    widget._registrar()

    assert criticals == [("Error", "No se pudo registrar la merma. Revisa el log.")]
    assert widget.container.db.execute("SELECT COUNT(*) FROM mermas").fetchone()[0] == 0
    widget.deleteLater()
    app.processEvents()


def test_merma_register_permission_validation_exception_is_reported(monkeypatch) -> None:
    app, widget = _qt_merma_widget()
    criticals = []

    from PyQt5.QtWidgets import QMessageBox
    from modulos.merma import SearchOption
    import core.permissions as permissions

    def broken_permission(*_args, **_kwargs):
        raise RuntimeError("permission store unavailable")

    monkeypatch.setattr(permissions, "verificar_permiso", broken_permission)
    monkeypatch.setattr(QMessageBox, "critical", lambda _parent, title, message, *args: criticals.append((title, message)))

    option = widget._buscar_productos("arra")[0]
    widget._on_producto_selected(SearchOption(id=option.id, label=option.label, subtitle=option.subtitle))
    widget.spin_cantidad.setValue(1.00)
    widget._registrar()

    assert criticals == [("Error", "No se pudo validar el permiso para registrar merma.")]
    assert widget.container.db.execute("SELECT COUNT(*) FROM mermas").fetchone()[0] == 0
    widget.deleteLater()
    app.processEvents()
