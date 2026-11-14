"""La sesión abierta sigue al ancla de la estación (SDLC-SET-001).

Anclar la sucursal se decide en Configuración, pero quien sabe mover la sesión es
el shell: contexto del router, barra superior y de estado, menú y el
`LegacySessionAdapter` que comparten todos los módulos. Las vistas se reconstruyen
en cada navegación y leen la sucursal de ese adaptador, así que basta con moverlo.
"""
from __future__ import annotations

import logging

from backend.bootstrap.application_context_errors import (
    BranchNotFoundError,
    ContextSwitchNotAllowedError,
)
from frontend.desktop.shell.router.errors import NavigationDeniedError

logger = logging.getLogger("spj.session")


class InstallationBranchFollower:
    def __init__(self, *, context_service, session_context, resolve_sidebar_items) -> None:
        self._service = context_service
        self._session = session_context
        self._resolve_sidebar_items = resolve_sidebar_items
        self._window = None

    def attach(self, window) -> None:
        self._window = window

    def follow(self, branch_id: str) -> tuple[bool, str]:
        """Mueve la sesión al sitio anclado. `False` significa que la sesión no
        puede seguirlo y hay que cerrarla (`end_session()`): el ancla ya cambió."""
        window = self._window
        try:
            context = self._service.follow_installation_anchor(
                window.router.current_context, branch_id=branch_id)
        except (ContextSwitchNotAllowedError, BranchNotFoundError) as exc:
            logger.warning("La sesión no puede seguir al ancla %s: %s", branch_id, exc)
            return False, f"{exc}\n\nHay que cerrar la sesión para continuar."

        self._session.rebind(context)
        window.update_context(context)
        items = self._resolve_sidebar_items(context)
        window.sidebar.set_items(items)
        logger.info("La sesión pasó a %s al re-anclar la estación.", context.branch_name)
        message = f"La sesión ya opera en «{context.branch_name}»."
        if window.router.current_route_still_allowed():
            return True, message
        return self._leave_denied_route(items, message)

    def _leave_denied_route(self, items, message: str) -> tuple[bool, str]:
        """En el sitio nuevo el usuario ya no puede ver esta pantalla."""
        if items:
            try:
                self._window.navigate(items[0].route_id)
                return True, message
            except NavigationDeniedError:
                logger.warning("Ruta %s rechazada tras re-anclar.", items[0].route_id)
        return False, ("Su usuario no tiene módulos disponibles en esta sucursal.\n\n"
                       "Hay que cerrar la sesión para continuar.")

    def end_session(self) -> None:
        self._window.logout_requested.emit()
