# modulos/whatsapp/widgets/error_panel.py
"""ErrorPanel — panel para mostrar errores con opción de reintentar."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import spj_btn


class ErrorPanel(QWidget):
    """Panel de error colapsable con mensaje y botón de reintento opcional."""

    retry_clicked = pyqtSignal()

    def __init__(self, message: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setVisible(bool(message))
        self.setStyleSheet(
            f"QWidget {{"
            f"  background: {Colors.DANGER.BG_SOFT};"
            f"  border: 1px solid {Colors.DANGER.BORDER};"
            f"  border-radius: {Borders.RADIUS_LG}px;"
            f"}}"
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.MD, Spacing.SM, Spacing.MD, Spacing.SM)
        lay.setSpacing(Spacing.XS)

        self._lbl_msg = QLabel()
        self._lbl_msg.setWordWrap(True)
        self._lbl_msg.setStyleSheet(
            f"color: {Colors.DANGER.BASE};"
            f"font-size: {Typography.SIZE_MD};"
            "background: transparent; border: none;"
        )

        self._lbl_detail = QLabel()
        self._lbl_detail.setWordWrap(True)
        self._lbl_detail.setStyleSheet(
            f"color: {Colors.DANGER.ACTIVE};"
            f"font-size: {Typography.SIZE_SM};"
            "background: transparent; border: none;"
        )
        self._lbl_detail.setVisible(False)

        self._btn_retry = QPushButton("🔄 Reintentar")
        spj_btn(self._btn_retry, "danger")
        self._btn_retry.setVisible(False)
        self._btn_retry.clicked.connect(self.retry_clicked)

        lay.addWidget(self._lbl_msg)
        lay.addWidget(self._lbl_detail)
        lay.addWidget(self._btn_retry, 0, Qt.AlignLeft)

        if message:
            self.set_error(message)

    def set_error(self, message: str, details: str = "", show_retry: bool = False) -> None:
        self._lbl_msg.setText(f"⚠️  {message}")
        if details:
            self._lbl_detail.setText(details)
            self._lbl_detail.setVisible(True)
        else:
            self._lbl_detail.setVisible(False)
        self._btn_retry.setVisible(show_retry)
        self.setVisible(True)

    def clear(self) -> None:
        self._lbl_msg.clear()
        self._lbl_detail.clear()
        self.setVisible(False)
