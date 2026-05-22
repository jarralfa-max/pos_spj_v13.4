# modulos/whatsapp/panels/history_panel.py
"""Panel Historial — búsqueda y visualización de mensajes WA."""
from __future__ import annotations

import logging

from PyQt5.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography
from modulos.spj_styles import spj_btn, apply_object_names
from modulos.whatsapp.panels._panel_styles import input_style
from modulos.whatsapp.widgets import EmptyState, ErrorPanel

logger = logging.getLogger("spj.ui.wa.history_panel")


class HistoryPanel(QWidget):
    """Historial de mensajes WA con búsqueda y filtros."""

    def __init__(self, svc, parent=None) -> None:
        super().__init__(parent)
        self._svc = svc
        self._build_ui()
        apply_object_names(self)
        self._load()

    # ── Construcción UI ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # Barra de controles
        ctrl = QHBoxLayout()
        ctrl.setSpacing(Spacing.SM)

        self._inp_search = QLineEdit()
        self._inp_search.setPlaceholderText("Buscar por número, mensaje o estado…")
        self._inp_search.setStyleSheet(input_style())
        self._inp_search.returnPressed.connect(self._load)

        self._cmb_dir = QComboBox()
        self._cmb_dir.addItems(["Todos", "Entrante", "Saliente"])
        self._cmb_dir.currentIndexChanged.connect(self._load)

        self._cmb_limit = QComboBox()
        self._cmb_limit.addItems(["50", "100", "200", "500"])

        btn_search  = QPushButton("Buscar")
        btn_refresh = QPushButton("Actualizar")
        spj_btn(btn_search, "primary", "sm")
        spj_btn(btn_refresh, "secondary", "sm")
        btn_search.clicked.connect(self._load)
        btn_refresh.clicked.connect(self._load)

        ctrl.addWidget(self._inp_search, 1)
        ctrl.addWidget(QLabel("Dirección:"))
        ctrl.addWidget(self._cmb_dir)
        ctrl.addWidget(QLabel("Límite:"))
        ctrl.addWidget(self._cmb_limit)
        ctrl.addWidget(btn_search)
        ctrl.addWidget(btn_refresh)
        root.addLayout(ctrl)

        self._err = ErrorPanel()
        root.addWidget(self._err)

        # Tabla
        self._tbl = QTableWidget()
        self._tbl.setColumnCount(5)
        self._tbl.setHorizontalHeaderLabels(
            ["Fecha", "Número", "Dirección", "Mensaje", "Estado"]
        )
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        for i in (0, 1, 2, 4):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.verticalHeader().setVisible(False)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setStyleSheet(
            f"QTableWidget {{ font-size: {Typography.SIZE_MD}; }}"
        )
        root.addWidget(self._tbl)

        self._empty = EmptyState(
            "📨",
            "Sin mensajes en el historial",
            "Los mensajes aparecerán aquí cuando se procesen.",
        )
        self._empty.setVisible(False)
        root.addWidget(self._empty)

        # Conteo
        self._lbl_count = QLabel("")
        self._lbl_count.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_400};"
            f"font-size: {Typography.SIZE_SM};"
        )
        root.addWidget(self._lbl_count)

    # ── Datos ─────────────────────────────────────────────────────────────────

    def _load(self) -> None:
        try:
            self._err.clear()
            search = self._inp_search.text().strip()
            limit  = int(self._cmb_limit.currentText())
            dir_filter = self._cmb_dir.currentText()

            kwargs: dict = {"search": search, "limit": limit}
            if dir_filter != "Todos":
                kwargs["direccion"] = dir_filter.lower()

            rows = self._svc.get_history(**kwargs)
            self._tbl.setRowCount(0)
            for i, r in enumerate(rows):
                self._tbl.insertRow(i)
                for j, key in enumerate(
                    ["fecha", "numero", "direccion", "mensaje", "estado"]
                ):
                    self._tbl.setItem(i, j, QTableWidgetItem(str(r.get(key) or "")))

            has_rows = bool(rows)
            self._tbl.setVisible(has_rows)
            self._empty.setVisible(not has_rows)
            self._lbl_count.setText(
                f"{len(rows)} mensaje(s)" if has_rows else ""
            )
        except Exception as exc:
            logger.debug("HistoryPanel._load: %s", exc)
            self._err.set_error(f"Error cargando historial: {exc}")

    def refresh(self) -> None:
        self._load()
