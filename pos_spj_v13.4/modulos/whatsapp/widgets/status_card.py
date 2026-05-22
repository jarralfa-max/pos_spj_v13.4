# modulos/whatsapp/widgets/status_card.py
"""StatusCard y MetricCard — tarjetas de estado y métricas."""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout, QHBoxLayout

from modulos.design_tokens import Colors, Spacing, Typography, Borders


class StatusCard(QFrame):
    """Tarjeta que muestra un título y un valor con indicador de estado."""

    def __init__(self, title: str, value: str = "—", parent=None) -> None:
        super().__init__(parent)
        self._setup_style()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        lay.setSpacing(Spacing.XS)

        self._lbl_title = QLabel(title)
        self._lbl_title.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f"font-size: {Typography.SIZE_SM};"
            f"font-weight: {Typography.WEIGHT_MEDIUM};"
        )

        self._lbl_value = QLabel(value)
        self._lbl_value.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_800};"
            f"font-size: {Typography.SIZE_XL};"
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        self._lbl_value.setWordWrap(True)

        lay.addWidget(self._lbl_title)
        lay.addWidget(self._lbl_value)

    def _setup_style(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: {Colors.NEUTRAL.WHITE};"
            f"  border: 1px solid {Colors.NEUTRAL.SLATE_200};"
            f"  border-radius: {Borders.RADIUS_XL}px;"
            f"}}"
        )

    def set_value(self, value: str) -> None:
        self._lbl_value.setText(value)

    def set_status(self, ok: bool) -> None:
        color = Colors.SUCCESS.BASE if ok else Colors.DANGER.BASE
        self._lbl_value.setStyleSheet(
            f"color: {color};"
            f"font-size: {Typography.SIZE_XL};"
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )


class MetricCard(QFrame):
    """Tarjeta compacta con valor destacado y subtítulo."""

    def __init__(
        self,
        title: str,
        value: str = "0",
        subtitle: str = "",
        accent: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._accent = accent or Colors.PRIMARY.BASE
        self._setup_style()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        lay.setSpacing(Spacing.XS)

        self._lbl_title = QLabel(title)
        self._lbl_title.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_500};"
            f"font-size: {Typography.SIZE_SM};"
            f"font-weight: {Typography.WEIGHT_MEDIUM};"
            "border: none; background: transparent;"
        )

        self._lbl_value = QLabel(value)
        self._lbl_value.setStyleSheet(
            f"color: {self._accent};"
            f"font-size: 22px;"
            f"font-weight: {Typography.WEIGHT_BOLD};"
            "border: none; background: transparent;"
        )

        self._lbl_sub = QLabel(subtitle)
        self._lbl_sub.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_400};"
            f"font-size: {Typography.SIZE_XS};"
            "border: none; background: transparent;"
        )

        lay.addWidget(self._lbl_title)
        lay.addWidget(self._lbl_value)
        if subtitle:
            lay.addWidget(self._lbl_sub)

    def _setup_style(self) -> None:
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet(
            f"QFrame {{"
            f"  background: {Colors.NEUTRAL.WHITE};"
            f"  border: 1px solid {Colors.NEUTRAL.SLATE_200};"
            f"  border-radius: {Borders.RADIUS_XL}px;"
            f"}}"
        )

    def set_value(self, value: str, subtitle: str = "") -> None:
        self._lbl_value.setText(value)
        if subtitle:
            self._lbl_sub.setText(subtitle)
            self._lbl_sub.setVisible(True)
