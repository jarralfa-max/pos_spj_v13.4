"""Compat wrapper: Tesorería ahora es submódulo de FINANZAS.

Este archivo existe para imports legacy y evita módulos paralelos.
"""
from __future__ import annotations

from modulos.finanzas_unificadas import ModuloFinanzasUnificadas


class ModuloTesoreria(ModuloFinanzasUnificadas):
    """Vista de compatibilidad que abre directamente la pestaña Tesorería."""

    def __init__(self, container, parent=None):
        super().__init__(container, parent)
        self.set_active_submodule("tesoreria")
