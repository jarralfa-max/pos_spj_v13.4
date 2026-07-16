"""Wrapper legacy: módulo FINANZAS.

La implementación vive en ``frontend/desktop/modules/finance`` (bounded
context financiero). Este archivo solo preserva imports legacy de navegación.
"""
from __future__ import annotations

from frontend.desktop.modules.finance.finance_routes import create_finance_view


class ModuloFinanzas:
    """Factory-compatible: ``ModuloFinanzas(container)`` devuelve la vista nueva."""

    def __new__(cls, container, parent=None):
        return create_finance_view(container, parent)
