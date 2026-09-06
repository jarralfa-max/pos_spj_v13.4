"""Lectura de la sesión viva para los `ModuleActivator` del shell.

Los activators reciben un `session_context` y necesitan siempre lo mismo:
quién es, en qué sucursal está y qué puede ver el sidebar INTERNO del módulo
(el `SidebarResolver` ya filtró la entrada al módulo con
`required_permission`; esto gobierna las secciones de dentro).

Existe porque esa derivación se copió activator a activator y la copia traía
un error: sondeaba `has_permission`/`permissions`, atributos que NINGUNA de
las dos sesiones vivas define —`core/session_context.py::SessionContext` y
`backend/bootstrap/legacy_session_adapter.py::LegacySessionAdapter` exponen
`tiene_permiso()`/`permisos`—, de modo que el callback devolvía False
siempre y el sidebar del módulo salía vacío. Un solo sitio en vez de N
copias evita que la siguiente plantilla vuelva a heredarlo (§26).

No sustituye a los `<Contexto>SessionPermissionChecker` de
`backend/application/*/session_authorization.py`: aquéllos son la
autorización real, revalidada por caso de uso y acotada por usuario. Esto
sólo decide qué se dibuja.
"""

from __future__ import annotations

from typing import Callable, Optional


def sidebar_permission_checker(session_context) -> Callable[[str], bool]:
    """Callback de visibilidad para el sidebar interno de un módulo.

    Sin sesión no concede nada: mostrar de más es peor que mostrar de menos.
    """
    if session_context is None:
        return lambda _permission: False

    checker = getattr(session_context, "tiene_permiso", None)
    if callable(checker):
        return lambda permission: bool(checker(permission))

    def _from_permission_codes(permission: str) -> bool:
        codes = getattr(session_context, "permisos", None)
        if codes is None:
            return False
        granted = {str(code).upper() for code in codes}
        return "*" in granted or str(permission).upper() in granted

    return _from_permission_codes


def active_branch_id(session_context) -> Optional[str]:
    """Sucursal activa. `active_branch_id` es la fuente canónica (UUID str);
    `sucursal_id` es su espejo declarado en `SessionContext`, y se conserva
    como respaldo para sesiones que sólo expongan el nombre viejo.
    """
    if session_context is None:
        return None
    for attribute in ("active_branch_id", "sucursal_id", "branch_id"):
        value = getattr(session_context, attribute, None)
        if value:
            return str(value)
    return None


def actor_user_id(session_context) -> Optional[str]:
    if session_context is None:
        return None
    value = getattr(session_context, "user_id", None)
    return str(value) if value else None
