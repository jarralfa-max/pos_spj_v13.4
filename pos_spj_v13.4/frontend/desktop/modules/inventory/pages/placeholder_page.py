"""PlaceholderPage (INV-25 / §54) — DS-consistent stand-in for a sidebar section.

The enterprise inventory sidebar exposes all 21 canonical sections from day one;
sections whose interactive page is not built yet render this placeholder instead
of a blank slot or a saturated catch-all window. It is presentation-only: a
``PageHeader`` plus a ``SectionCard`` with an informational message — no data
access, no business logic, no fabricated content.
"""

from __future__ import annotations

from PyQt5.QtWidgets import QLabel, QVBoxLayout, QWidget

from frontend.desktop.components import PageHeader, SectionCard
from frontend.desktop.components.icons import Icons
from frontend.desktop.themes.tokens import Spacing


class PlaceholderPage(QWidget):
    """Presentation-only placeholder for a not-yet-built inventory section."""

    def __init__(self, title: str, subtitle: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("inventoryPlaceholderPage")
        self._title = title

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.MD)

        self.header = PageHeader(title=title, subtitle=subtitle,
                                 icon=getattr(Icons, "INVENTORY", None), compact=True)
        layout.addWidget(self.header)

        card = SectionCard(title="Sección en preparación")
        message = QLabel(
            f"«{title}» estará disponible próximamente en el módulo de inventario "
            "enterprise. La navegación y los permisos ya están habilitados.")
        message.setWordWrap(True)
        message.setProperty("role", "muted")
        card.add(message)
        layout.addWidget(card)
        layout.addStretch(1)

    def refresh(self) -> None:  # noqa: D401 — contrato de página (no-op)
        """Sin datos que refrescar; existe para cumplir el contrato de página."""
