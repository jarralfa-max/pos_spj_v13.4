# modulos/whatsapp/panels/policies_panel.py
"""Panel de Políticas — tabla de solo lectura con la política de canales WA."""
from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from modulos.design_tokens import Colors, Spacing, Typography, Borders
from modulos.spj_styles import apply_object_names
from modulos.whatsapp.panels._panel_styles import info_banner_style
from modulos.whatsapp.widgets import PolicyTable


class PoliciesPanel(QWidget):
    """
    Panel informativo de política de notificaciones WA.
    Solo lectura — la fuente de verdad es NotificationPolicyService.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._build_ui()
        apply_object_names(self)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        root.setSpacing(Spacing.MD)

        # Título
        lbl_title = QLabel("Política de canales de notificación")
        lbl_title.setStyleSheet(
            f"font-size: {Typography.SIZE_XXL};"
            f"font-weight: {Typography.WEIGHT_SEMIBOLD};"
        )
        root.addWidget(lbl_title)

        # Descripción
        lbl_desc = QLabel(
            "Esta tabla define qué eventos se envían por WhatsApp al staff y cuáles "
            "quedan solo en el ERP inbox. La política es fija y se aplica en "
            "<b>NotificationPolicyService</b>. Los eventos de cliente siempre van por WA."
        )
        lbl_desc.setWordWrap(True)
        lbl_desc.setStyleSheet(
            f"font-size: {Typography.SIZE_MD};"
        )
        root.addWidget(lbl_desc)

        # Leyenda
        legend_row = QLabel(
            "  <b>✅ WA</b> — Se envía por WhatsApp al staff destinatario"
            "&nbsp;&nbsp;&nbsp;"
            "<b>❌ Solo inbox</b> — Solo aparece en el ERP inbox, sin WA al staff"
            "&nbsp;&nbsp;&nbsp;"
            "<b>✅ Inbox</b> — Siempre registrado en ERP inbox"
        )
        legend_row.setWordWrap(True)
        legend_row.setStyleSheet(info_banner_style("neutral"))
        root.addWidget(legend_row)

        # Tabla de política
        root.addWidget(PolicyTable())

        # Nota al pie
        note = QLabel(
            "* Para modificar la política, editar "
            "<code>core/services/notifications/notification_policy_service.py</code>."
        )
        note.setStyleSheet(f"font-size: {Typography.SIZE_XS};")
        root.addWidget(note)
