"""Canonical HR settings page shell."""

from __future__ import annotations

from PyQt5.QtWidgets import QVBoxLayout, QWidget

from frontend.desktop.components import EmptyState, Icons, PageHeader
from frontend.desktop.themes import DesktopSpacing


class HRSettingsPage(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG, DesktopSpacing.LG)
        layout.setSpacing(DesktopSpacing.MD)
        layout.addWidget(
            PageHeader(
                title="Configuración RRHH",
                subtitle="Catálogos, permisos y parámetros del módulo canónico.",
                icon=Icons.SETTINGS,
                parent=self,
            )
        )
        layout.addWidget(
            EmptyState(
                "Configuración canónica en preparación",
                "Los catálogos disponibles se administran mediante use cases y permisos RRHH.",
                self,
            )
        )
        layout.addStretch(1)
