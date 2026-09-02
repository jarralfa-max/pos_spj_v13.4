"""Wrapper legacy: módulo Tarjetas Fidelidad enterprise (LOY-25).

La implementación vive en ``frontend/desktop/modules/tarjetas_fidelidad``
(bounded context Loyalty Cards). Mirrors ``modulos/fidelidad_enterprise.py``'s
exact shape — el desempaquetado del contenedor ocurre EN ESTE archivo.

Módulo NUEVO, adicional al legacy ``modulos/tarjetas.py``
(``_conectar("TARJETAS_FIDELIDAD", ModuloTarjetas, ...)``) — no lo
reemplaza todavía, misma decisión y mismo motivo documentados en
``modulos/fidelidad_enterprise.py``.
"""
from __future__ import annotations

from frontend.desktop.modules.tarjetas_fidelidad.composition import (
    create_tarjetas_fidelidad_view,
)


class ModuloTarjetasFidelidadEnterprise:
    """Factory-compatible: ``ModuloTarjetasFidelidadEnterprise(container)``
    devuelve la vista nueva."""

    def __new__(cls, container, parent=None):
        connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
        session_context = getattr(container, "session", None)
        return create_tarjetas_fidelidad_view(connection, session_context, parent)
