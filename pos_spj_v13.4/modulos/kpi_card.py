# modulos/kpi_card.py
"""Reusable KPI card component for all modules."""
from __future__ import annotations
from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PyQt5.QtCore import Qt
from modulos.design_tokens import Colors, Typography


class KPICard(QFrame):
    """Theme-aware operational KPI card with accent bar and icon."""

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
        self.setMinimumHeight(86)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame(self)
        bar.setFixedHeight(3)
        bar.setStyleSheet(
            f"background: {_accent}; border: none;"
            f" border-top-left-radius: 12px; border-top-right-radius: 12px;"
        )
        outer.addWidget(bar)

        body = QHBoxLayout()
        body.setContentsMargins(14, 10, 14, 10)
        body.setSpacing(8)
        outer.addLayout(body)

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
        self.lbl_valor.setStyleSheet(
            f"font-size: 22px; font-weight: {Typography.WEIGHT_BOLD};"
            f" letter-spacing: -0.02em; background: transparent; border: none;"
        )
        col.addWidget(self.lbl_valor)
        body.addLayout(col, 1)

        lbl_icon = QLabel(icono)
        lbl_icon.setFixedSize(36, 36)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(
            f"font-size: 18px; background: {_accent}1A;"
            f" border-radius: 18px; border: none;"
        )
        body.addWidget(lbl_icon, 0, alignment=Qt.AlignTop)

    def set_valor(self, v: str):
        self.lbl_valor.setText(v)
