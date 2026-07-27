# modulos/compras/items_table.py — SPJ POS v13.4
"""
ItemsTable — self-contained cart table widget for the purchase form.

Signals:
    items_changed(list)   — emitted after any add/edit/remove; payload is full cart list
    producto_requested    — emitted when user opens product search (F2 / button)

Usage:
    table = ItemsTable(parent=self)
    table.items_changed.connect(self._on_items_changed)
    table.set_items(carrito_compra)
"""
from __future__ import annotations
from typing import Callable
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal
from modulos.design_tokens import Colors, Spacing, Typography, Borders


class ItemsTable(QWidget):
    """
    Cart table for purchase items.
    Columns: SKU/ID | Producto | Lote | Cant./UM | Peso Est. | Costo | Desc/Imp | Subtotal | (del)

    All business logic (price validation, recipe detection, etc.) stays in
    ModuloComprasPro. This widget only manages display and emits signals.
    """
    items_changed = pyqtSignal(list)

    COLUMNS = ["SKU/ID", "Producto", "Lote", "Cant./UM", "Peso Est.", "Costo", "Desc/Imp", "Subtotal", ""]
    COL_COUNT = len(COLUMNS)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[dict] = []
        self._edit_callback: Callable | None = None
        self._build_ui()

    def set_edit_callback(self, fn: Callable) -> None:
        """Set the function called when user double-clicks a row (receives row index)."""
        self._edit_callback = fn

    def set_items(self, items: list[dict]) -> None:
        self._items = list(items)
        self._refresh()

    def get_items(self) -> list[dict]:
        return list(self._items)

    def clear(self) -> None:
        self._items = []
        self._refresh()
        self.items_changed.emit([])

    def add_item(self, item: dict) -> None:
        self._items.append(item)
        self._refresh()
        self.items_changed.emit(list(self._items))

    def remove_item(self, row: int) -> None:
        if 0 <= row < len(self._items):
            self._items.pop(row)
            self._refresh()
            self.items_changed.emit(list(self._items))

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Header row
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(Spacing.XS, Spacing.XS, Spacing.XS, Spacing.XS)
        hdr_row.setSpacing(Spacing.XS)
        lbl = QLabel("PARTIDAS DE COMPRA")
        lbl.setStyleSheet(
            f"color:{Colors.NEUTRAL.SLATE_700};font-size:{Typography.SIZE_XS};"
            f"font-weight:{Typography.WEIGHT_BOLD};letter-spacing:0.1em;"
            "background:transparent;border:none;"
        )
        self._lbl_count = QLabel("0 items")
        self._lbl_count.setObjectName("caption")
        self._lbl_count.setStyleSheet(
            f"color:{Colors.NEUTRAL.SLATE_500};background:transparent;border:none;"
        )
        hdr_row.addWidget(lbl)
        hdr_row.addWidget(self._lbl_count)
        hdr_row.addStretch()

        hdr_frame = QFrame()
        hdr_frame.setStyleSheet(
            f"QFrame{{border-bottom:1px solid {Colors.NEUTRAL.SLATE_200};}}"
        )
        hdr_frame.setLayout(hdr_row)
        lay.addWidget(hdr_frame)

        # Table
        self.tabla = QTableWidget()
        self.tabla.setColumnCount(self.COL_COUNT)
        self.tabla.setHorizontalHeaderLabels(self.COLUMNS)
        hh = self.tabla.horizontalHeader()
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        for c in (0, 2, 3, 4, 5, 6, 7, 8):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        hh.setStyleSheet(
            f"QHeaderView::section{{"
            f"  background:{Colors.NEUTRAL.SLATE_100};"
            f"  color:{Colors.NEUTRAL.SLATE_500};"
            f"  font-size:9px;font-weight:700;"
            f"  letter-spacing:0.06em;"
            f"  border:none;border-bottom:1px solid {Colors.NEUTRAL.SLATE_200};"
            f"  padding:4px 6px;"
            f"}}"
        )
        self.tabla.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabla.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabla.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tabla.setAlternatingRowColors(True)
        self.tabla.setShowGrid(False)
        self.tabla.verticalHeader().setVisible(False)
        self.tabla.doubleClicked.connect(self._on_double_click)
        self.tabla.setObjectName("tableView")
        lay.addWidget(self.tabla, 1)

    def _refresh(self) -> None:
        self.tabla.setRowCount(0)
        for row_idx, it in enumerate(self._items):
            self.tabla.insertRow(row_idx)
            cols = [
                str(it.get("codigo") or it.get("producto_id", "")),
                str(it.get("nombre", "")),
                str(it.get("lote", "")),
                f"{it.get('cantidad', 1):.2f} {it.get('unidad', 'pz')}",
                f"{it.get('peso_estimado', 0):.2f} kg" if it.get("peso_estimado") else "—",
                f"${float(it.get('costo_unitario', 0)):.2f}",
                f"${float(it.get('descuento', 0)):.2f}",
                f"${float(it.get('subtotal', 0)):.2f}",
            ]
            for col, val in enumerate(cols):
                cell = QTableWidgetItem(val)
                cell.setTextAlignment(Qt.AlignVCenter | (Qt.AlignRight if col >= 3 else Qt.AlignLeft))
                self.tabla.setItem(row_idx, col, cell)

            # Delete button
            btn_del = QPushButton("✕")
            btn_del.setFixedSize(22, 22)
            btn_del.setStyleSheet(
                f"QPushButton{{background:transparent;color:{Colors.DANGER_BASE};"
                f"border:none;font-weight:700;}}"
                f"QPushButton:hover{{background:{Colors.DANGER_BASE}20;border-radius:3px;}}"
            )
            btn_del.clicked.connect(lambda _, r=row_idx: self.remove_item(r))
            self.tabla.setCellWidget(row_idx, self.COL_COUNT - 1, btn_del)

        n = len(self._items)
        self._lbl_count.setText(f"{n} item{'s' if n != 1 else ''}")

    def _on_double_click(self, index) -> None:
        if self._edit_callback:
            self._edit_callback(index)
