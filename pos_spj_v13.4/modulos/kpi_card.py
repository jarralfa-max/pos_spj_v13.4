# modulos/kpi_card.py
"""Reusable KPI card component for all modules (theme-aware)."""
from __future__ import annotations
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt
from modulos.design_tokens import Colors, Typography, Borders
from modulos import bi_theme

_ACCENTS = {
    "primary": Colors.PRIMARY.BASE,
    "success": Colors.SUCCESS.BASE,
    "danger": Colors.DANGER.BASE,
    "warning": Colors.WARNING.BASE,
    "info": Colors.INFO.BASE,
}


class KPICard(QFrame):
    """Theme-aware operational KPI card with accent bar and icon.

    Surface colors (bg/border/text) come from the design tokens per theme
    (`bi_theme.surface`); the accent bar and icon badge use the variant token
    color (theme-independent). Pass `theme='dark'|'light'` or call `set_theme()`
    to switch. Default 'dark' preserves the historical look for existing callers.
    """

    def __init__(self, titulo: str, valor: str = "—",
                 icono: str = "📦", variant: str = "primary",
                 parent=None, theme: str = "dark"):
        super().__init__(parent)
        self._variant = variant
        self._theme = bi_theme.normalize_theme(theme)
        self._accent = _ACCENTS.get(variant, Colors.PRIMARY.BASE)

        self.setObjectName("kpiCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(92)
        self.setMaximumHeight(112)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._bar = QFrame(self)
        self._bar.setFixedHeight(3)
        outer.addWidget(self._bar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 8, 14, 8)
        body.setSpacing(8)
        outer.addLayout(body, 1)

        col = QVBoxLayout()
        col.setSpacing(2)

        self.lbl_t = QLabel(titulo.upper())
        col.addWidget(self.lbl_t)

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setMinimumHeight(34)
        self.lbl_valor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        col.addWidget(self.lbl_valor, 1)
        body.addLayout(col, 1)

        self.lbl_icon = QLabel(icono)
        self.lbl_icon.setFixedSize(36, 36)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        body.addWidget(self.lbl_icon, 0, alignment=Qt.AlignTop)

        self._apply_style()

    def _apply_style(self):
        pal = bi_theme.surface(self._theme)
        accent = self._accent
        hover_bg = pal["border"]  # ligeramente distinto al card
        self.setStyleSheet(
            f"QFrame#kpiCard {{"
            f"background-color: {pal['card']};"
            f"border: 1px solid {pal['border']};"
            f"border-radius: {Borders.RADIUS_LG}px;"
            f"min-height: 92px; max-height: 112px;"
            f"}}"
            f"QFrame#kpiCard:hover {{"
            f"background-color: {hover_bg};"
            f"border-color: {accent};"
            f"}}"
        )
        self._bar.setStyleSheet(
            f"background: {accent}; border: none;"
            f" border-top-left-radius: {Borders.RADIUS_LG}px;"
            f" border-top-right-radius: {Borders.RADIUS_LG}px;"
        )
        self.lbl_t.setStyleSheet(
            f"color: {pal['muted']}; font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; letter-spacing: 0.08em;"
            f" background: transparent; border: none;"
        )
        self.lbl_valor.setStyleSheet(
            f"color: {pal['text']};"
            f"font-size: {Typography.SIZE_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em; background: transparent; border: none;"
        )
        self.lbl_icon.setStyleSheet(
            f"font-size: {Typography.SIZE_XXXL}; background: {accent}1A;"
            f" border-radius: 18px; border: none;"
        )

    def set_theme(self, theme: str):
        """Cambia el tema de la tarjeta (claro/oscuro) y re-estiliza."""
        nt = bi_theme.normalize_theme(theme)
        if nt != self._theme:
            self._theme = nt
            self._apply_style()

    def set_valor(self, v: str):
        self.lbl_valor.setText(v)
