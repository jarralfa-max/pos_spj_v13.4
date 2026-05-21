# modulos/whatsapp/widgets/empty_state.py
"""EmptyState — widget para listas/tablas sin datos."""
from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from modulos.design_tokens import Colors, Spacing, Typography
from modulos.spj_styles import spj_btn


class EmptyState(QWidget):
    """Placeholder vacío con ícono, mensaje y acción opcional."""

    action_triggered = pyqtSignal()

    def __init__(
        self,
        icon: str = "📭",
        message: str = "Sin datos",
        description: str = "",
        action_text: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(Spacing.SM)
        lay.setContentsMargins(Spacing.XL, Spacing.XXL, Spacing.XL, Spacing.XXL)

        lbl_icon = QLabel(icon)
        lbl_icon.setAlignment(Qt.AlignCenter)
        lbl_icon.setStyleSheet(f"font-size: 36px; background: transparent;")

        lbl_msg = QLabel(message)
        lbl_msg.setAlignment(Qt.AlignCenter)
        lbl_msg.setStyleSheet(
            f"color: {Colors.NEUTRAL.SLATE_600};"
            f"font-size: {Typography.SIZE_XL};"
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
            "background: transparent;"
        )

        lay.addWidget(lbl_icon)
        lay.addWidget(lbl_msg)

        if description:
            lbl_desc = QLabel(description)
            lbl_desc.setAlignment(Qt.AlignCenter)
            lbl_desc.setWordWrap(True)
            lbl_desc.setStyleSheet(
                f"color: {Colors.NEUTRAL.SLATE_400};"
                f"font-size: {Typography.SIZE_MD};"
                "background: transparent;"
            )
            lay.addWidget(lbl_desc)

        if action_text:
            btn = QPushButton(action_text)
            spj_btn(btn, "primary")
            btn.clicked.connect(self.action_triggered)
            lay.addWidget(btn, 0, Qt.AlignCenter)
