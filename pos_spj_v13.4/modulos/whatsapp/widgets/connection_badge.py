# modulos/whatsapp/widgets/connection_badge.py
"""StatusBadge y ConnectionBadge — indicadores visuales de estado de conexión."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from modulos.design_tokens import Colors, Spacing, Typography, Borders

_STATUS_STYLES: dict[str, tuple[str, str]] = {
    "ok":      (Colors.SUCCESS.BG_SOFT, Colors.SUCCESS.BASE),
    "warning": (Colors.WARNING.BG_SOFT, Colors.WARNING.BASE),
    "error":   (Colors.DANGER.BG_SOFT,  Colors.DANGER.BASE),
    "neutral": (Colors.NEUTRAL.SLATE_100, Colors.NEUTRAL.SLATE_500),
    "loading": (Colors.INFO.BG_SOFT,    Colors.INFO.BASE),
    "info":    (Colors.INFO.BG_SOFT,    Colors.INFO.BASE),
}


class StatusBadge(QLabel):
    """Pill de estado coloreado (fondo suave + texto)."""

    def __init__(self, text: str = "", status: str = "neutral", parent=None) -> None:
        super().__init__(parent)
        self.set_status(text, status)
        self.setAlignment(Qt.AlignCenter)

    def set_status(self, text: str, status: str = "neutral") -> None:
        bg, fg = _STATUS_STYLES.get(status, _STATUS_STYLES["neutral"])
        self.setText(text)
        self.setStyleSheet(
            f"QLabel {{"
            f"  background: {bg};"
            f"  color: {fg};"
            f"  border: 1px solid {fg};"
            f"  border-radius: {Borders.RADIUS_FULL}px;"
            f"  padding: {Spacing.XS}px {Spacing.SM}px;"
            f"  font-size: {Typography.SIZE_SM};"
            f"  font-weight: {Typography.WEIGHT_SEMIBOLD};"
            f"}}"
        )


class ConnectionBadge(QWidget):
    """Indicador de conexión con punto de color y etiqueta de texto."""

    _DOT_CONNECTED    = f"color: {Colors.SUCCESS.BASE}; font-size: 18px;"
    _DOT_DISCONNECTED = f"color: {Colors.DANGER.BASE};  font-size: 18px;"
    _DOT_LOADING      = f"color: {Colors.WARNING.BASE}; font-size: 18px;"

    def __init__(self, text: str = "Desconectado", parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(Spacing.SM)

        self._dot = QLabel("●")
        self._dot.setStyleSheet(self._DOT_DISCONNECTED)

        self._lbl = QLabel(text)
        self._lbl.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_700};"
            f"font-size: {Typography.SIZE_LG};"
            f"font-weight: {Typography.WEIGHT_MEDIUM};"
        )

        lay.addWidget(self._dot)
        lay.addWidget(self._lbl)
        lay.addStretch()

    def set_connected(self, connected: bool, text: str = "") -> None:
        if connected:
            self._dot.setStyleSheet(self._DOT_CONNECTED)
            self._lbl.setText(text or "Conectado")
        else:
            self._dot.setStyleSheet(self._DOT_DISCONNECTED)
            self._lbl.setText(text or "Desconectado")

    def set_loading(self, text: str = "Verificando…") -> None:
        self._dot.setStyleSheet(self._DOT_LOADING)
        self._lbl.setText(text)

    def set_text(self, text: str) -> None:
        self._lbl.setText(text)
