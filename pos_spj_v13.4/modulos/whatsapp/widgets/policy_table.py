# modulos/whatsapp/widgets/policy_table.py
"""PolicyTable — tabla de solo lectura con la política de canales WA."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QHeaderView, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from modulos.design_tokens import Colors, Spacing, Typography
from modulos.whatsapp.panels._panel_styles import table_style


_WA_POLICY: list[tuple[str, str, str]] = [
    # (tipo, canal_wa, canal_inbox)
    ("nomina_pagada",              "✅ WA",    "✅ Inbox"),
    ("vacaciones_recordatorio",    "✅ WA",    "✅ Inbox"),
    ("descanso_recordatorio",      "✅ WA",    "✅ Inbox"),
    ("diferencia_caja",            "✅ WA",    "✅ Inbox"),
    ("backup_fallido",             "✅ WA",    "✅ Inbox"),
    ("diferencia_recepcion",       "✅ WA",    "✅ Inbox"),
    ("alerta_seguridad",           "✅ WA",    "✅ Inbox"),
    ("alerta_operacion_critica",   "✅ WA",    "✅ Inbox"),
    ("pedido_asignado_repartidor", "✅ WA",    "✅ Inbox"),
    ("forecast_sugerencia_compra", "✅ WA",    "✅ Inbox"),
    # ── Bloqueados ─────────────────────────────────────────────────────────
    ("pedido_whatsapp_nuevo",      "❌ Solo inbox", "✅ Inbox"),
    ("anticipo_requerido",         "❌ Solo inbox", "✅ Inbox"),
    ("anticipo_recibido",          "❌ Solo inbox", "✅ Inbox"),
    ("pedido_cancelado",           "❌ Solo inbox", "✅ Inbox"),
    ("venta_cancelada",            "❌ Solo inbox", "✅ Inbox"),
    ("pedido_listo",               "❌ Solo inbox", "✅ Inbox"),
    ("venta_confirmada",           "❌ Solo inbox", "✅ Inbox"),
    ("cambio_estado_pedido",       "❌ Solo inbox", "✅ Inbox"),
    ("stock_bajo",                 "❌ Solo inbox", "✅ Inbox"),
    ("corte_z",                    "❌ Solo inbox", "✅ Inbox"),
    ("caducidad_proxima",          "❌ Solo inbox", "✅ Inbox"),
]

_COL_HEADERS = ["Tipo de evento", "Canal WA (staff)", "ERP Inbox"]


class PolicyTable(QWidget):
    """
    Tabla de solo lectura que muestra la política de canales por tipo de evento.
    La fuente de verdad es NotificationPolicyService — esta tabla es solo visual.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._tbl = QTableWidget()
        self._tbl.setColumnCount(len(_COL_HEADERS))
        self._tbl.setHorizontalHeaderLabels(_COL_HEADERS)
        self._tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._tbl.setAlternatingRowColors(True)
        self._tbl.verticalHeader().setVisible(False)
        hh = self._tbl.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        hh.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._tbl.setStyleSheet(table_style())
        self._populate()
        lay.addWidget(self._tbl)

    def _populate(self) -> None:
        from PyQt5.QtGui import QColor
        self._tbl.setRowCount(len(_WA_POLICY))
        for row, (tipo, wa_col, inbox_col) in enumerate(_WA_POLICY):
            allowed = wa_col.startswith("✅")
            self._tbl.setItem(row, 0, QTableWidgetItem(tipo))
            wa_item = QTableWidgetItem(wa_col)
            wa_item.setForeground(
                QColor(Colors.SUCCESS.BASE if allowed else Colors.DANGER.BASE)
            )
            wa_item.setTextAlignment(Qt.AlignCenter)
            inbox_item = QTableWidgetItem(inbox_col)
            inbox_item.setForeground(QColor(Colors.SUCCESS.BASE))
            inbox_item.setTextAlignment(Qt.AlignCenter)
            self._tbl.setItem(row, 1, wa_item)
            self._tbl.setItem(row, 2, inbox_item)
