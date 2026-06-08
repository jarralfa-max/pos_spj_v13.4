# modulos/kpi_card.py
"""Reusable KPI card component for all modules."""
from __future__ import annotations
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt
from modulos.design_tokens import Colors, Typography, Borders


class KPICard(QFrame):
    """Theme-aware operational KPI card with accent bar and icon.

    The component owns its vertical size so parent containers such as buttons,
    tab panes, or splitters cannot collapse the value area. This keeps the KPI
    bar visible in modules like Inventory without relying on per-module hacks.
    """

    def __init__(self, titulo: str, valor: str = "—",
                 icono: str = "📦", variant: str = "primary",
                 parent=None):
        super().__init__(parent)
        _accent = {
            "primary": Colors.PRIMARY.BASE,
            "success": Colors.SUCCESS.BASE,
            "danger": Colors.DANGER.BASE,
            "warning": Colors.WARNING.BASE,
            "info": Colors.INFO.BASE,
        }.get(variant, Colors.PRIMARY.BASE)

        self.setObjectName("kpiCard")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(92)
        self.setMaximumHeight(112)
        self.setStyleSheet(
            f"QFrame#kpiCard {{"
            f"background-color: {Colors.NEUTRAL.SLATE_800};"
            f"border: 1px solid {Colors.NEUTRAL.SLATE_700};"
            f"border-radius: {Borders.RADIUS_LG}px;"
            f"min-height: 92px;"
            f"max-height: 112px;"
            f"}}"
            f"QFrame#kpiCard:hover {{"
            f"background-color: #263548;"
            f"border-color: {Colors.PRIMARY.BASE};"
            f"}}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame(self)
        bar.setFixedHeight(3)
        bar.setStyleSheet(
            f"background: {_accent}; border: none;"
            f" border-top-left-radius: {Borders.RADIUS_LG}px; border-top-right-radius: {Borders.RADIUS_LG}px;"
        )
        outer.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 8, 14, 8)
        body.setSpacing(8)
        outer.addLayout(body, 1)

        col = QVBoxLayout()
        col.setSpacing(2)

        lbl_t = QLabel(titulo.upper())
        lbl_t.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500}; font-size: {Typography.SIZE_XS};"
            f" font-weight: {Typography.WEIGHT_SEMIBOLD}; letter-spacing: 0.08em;"
            f" background: transparent; border: none;"
        )
        col.addWidget(lbl_t)

        self.lbl_valor = QLabel(valor)
        self.lbl_valor.setObjectName("kpiValue")
        self.lbl_valor.setMinimumHeight(34)
        self.lbl_valor.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.lbl_valor.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_100};"
            f"font-size: {Typography.SIZE_DISPLAY}; font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em; background: transparent; border: none;"
        )
        col.addWidget(self.lbl_valor, 1)
        body.addLayout(col, 1)

        lbl_icon = QLabel(icono)
        lbl_icon.setFixedSize(36, 36)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(
            f"font-size: {Typography.SIZE_XXXL}; background: {_accent}1A;"
            f" border-radius: 18px; border: none;"
        )
        body.addWidget(lbl_icon, 0, alignment=Qt.AlignTop)

    def set_valor(self, v: str):
        self.lbl_valor.setText(v)
