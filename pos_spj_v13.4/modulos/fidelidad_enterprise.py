"""Wrapper legacy: módulo Fidelidad enterprise (LOY-25).

La implementación vive en ``frontend/desktop/modules/fidelidad`` (bounded
contexts Loyalty/Commercial Instruments/Sweepstakes). Mirrors
``modulos/clientes_crm.py``'s exact shape: el desempaquetado del contenedor
(``container.db``/``container.session``) ocurre EN ESTE archivo —
``frontend/desktop/modules/fidelidad/composition.py`` nunca recibe ni
referencia el contenedor de la app, solo una conexión y un contexto de
sesión ya extraídos.

Este es un módulo NUEVO, adicional al legacy ``modulos/fidelidad_config.py``
(``_conectar("GROWTH_ENGINE", ModuloFidelidadConfig, ...)`` en
``interfaz/main_window.py``) — DELIBERADAMENTE NO lo reemplaza todavía. El
legacy sigue siendo el único módulo enlazado a la barra lateral real; este
bridge existe para que el módulo nuevo sea instanciable/probable end-to-end
(ver ``docs/refactor/LOY-25_ui_ux.md`` para la decisión completa de no
hacer el corte todavía — la mayoría de las secciones del menú nuevo siguen
siendo marcadores de posición, y reemplazar el legacy hoy sería una
regresión real de funcionalidad visible para el usuario, prohibida por la
Prioridad 0 de CLAUDE.md).
"""
from __future__ import annotations

from frontend.desktop.modules.fidelidad.composition import create_fidelidad_view


class ModuloFidelidadEnterprise:
    """Factory-compatible: ``ModuloFidelidadEnterprise(container)`` devuelve
    la vista nueva."""

    def __new__(cls, container, parent=None):
        connection = getattr(container, "db", None) or getattr(container, "db_conn", None)
        session_context = getattr(container, "session", None)
        return create_fidelidad_view(connection, session_context, parent)
