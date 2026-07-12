# modulos/compras/actions_bar.py — SPJ POS v13.4
"""
ActionsBar — dynamic action button + secondary draft/send buttons.

Signals:
    autorizar_clicked   — main "Autorizar compra" / "Generar PR" button
    borrador_clicked    — save as draft
    enviar_clicked      — send to reception

Usage:
    bar = ActionsBar(parent=self)
    bar.autorizar_clicked.connect(self._procesar_compra)
    bar.set_estado("CAPTURA")   # updates button text/color per doctype
"""
from __future__ import annotations
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy,
)
from PyQt5.QtCore import pyqtSignal
from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.ui_components import (
    create_success_button, create_secondary_button,
)

_ESTADO_MAP = {
    "CAPTURA":  ("✓ Autorizar compra",       Colors.SUCCESS_BASE,  "Autorizar y procesar la compra"),
    "BORRADOR": ("✓ Autorizar compra",       Colors.SUCCESS_BASE,  "Autorizar y procesar la compra"),
    "PR":       ("📋 Generar Solicitud (PR)", Colors.INFO_BASE,    "Crear solicitud de compra"),
    "PO":       ("📦 Generar Orden (PO)",     Colors.PRIMARY_BASE, "Crear orden de compra formal"),
    "RECIBIR":  ("✓ Confirmar Recepción",    Colors.SUCCESS_BASE,  "Confirmar ingreso al inventario"),
}


class ActionsBar(QWidget):
    """
    Action bar for the purchase form.
    Shows a large primary action button and secondary draft/send row.
    """
    autorizar_clicked = pyqtSignal()
    borrador_clicked  = pyqtSignal()
    enviar_clicked    = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def set_estado(self, estado: str) -> None:
        """Refresca la etiqueta/color del botón según el tipo de documento actual."""
        lbl, color, tip = _ESTADO_MAP.get(estado.upper(), _ESTADO_MAP["CAPTURA"])
        self._btn_main.setText(lbl)
        self._btn_main.setToolTip(tip)
        self._btn_main.setStyleSheet(
            f"QPushButton{{background:{color};color:{Colors.NEUTRAL.WHITE};"
            f"border-radius:{Borders.RADIUS_MD}px;font-size:13px;font-weight:700;"
            f"letter-spacing:0.05em;border:none;}}"
            f"QPushButton:hover{{background:{color}CC;}}"
        )

    def set_enabled(self, enabled: bool) -> None:
        self._btn_main.setEnabled(enabled)

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.XS)

        # Secondary row
        sec_row = QHBoxLayout()
        sec_row.setSpacing(Spacing.XS)
        self._btn_borrador = create_secondary_button(self, "💾 Borrador", "Guardar como borrador")
        self._btn_borrador.setMinimumHeight(32)
        self._btn_borrador.clicked.connect(self.borrador_clicked.emit)

        self._btn_enviar = create_success_button(
            self, "📨 Enviar a recepción", "Registrar y enviar a almacén")
        self._btn_enviar.setMinimumHeight(32)
        self._btn_enviar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_enviar.clicked.connect(self.enviar_clicked.emit)

        sec_row.addWidget(self._btn_borrador)
        sec_row.addWidget(self._btn_enviar, 1)
        lay.addLayout(sec_row)

        # Main action button
        self._btn_main = create_success_button(self, "✓ Autorizar compra", "Autorizar y procesar")
        self._btn_main.setMinimumHeight(48)
        self._btn_main.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._btn_main.clicked.connect(self.autorizar_clicked.emit)
        lay.addWidget(self._btn_main)

        # Hint
        self._lbl_hint = QLabel(
            "Flujo: Capturar → Generar PR → Aprobar PR → Generar PO → Procesar")
        from PyQt5.QtCore import Qt
        self._lbl_hint.setAlignment(Qt.AlignCenter)
        self._lbl_hint.setStyleSheet(
            f"font-size:9px;font-style:italic;color:{Colors.NEUTRAL.SLATE_400};"
            "background:transparent;"
        )
        lay.addWidget(self._lbl_hint)
