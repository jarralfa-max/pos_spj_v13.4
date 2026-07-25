"""Category hierarchy policy (P1-01) — pura: rutas, profundidad y anti-ciclo.

La ruta materializada tiene la forma ``/id_raiz/.../id_propio/`` (siempre empieza y
termina en ``/``), lo que hace triviales las consultas de subárbol (``LIKE
'/id/%'``) y la detección de ciclos (un padre no puede estar dentro del subárbol de
la categoría que se mueve). No toca persistencia.
"""

from __future__ import annotations

from backend.domain.products.exceptions import (
    CategoryCycleDetectedError,
    CategoryDepthExceededError,
)

#: Profundidad máxima del árbol (raíz = 0). Evita jerarquías inmanejables.
MAX_DEPTH = 5


def child_path(parent_path: str | None, category_id: str) -> str:
    """Ruta materializada de una categoría dado el path de su padre (o None si raíz)."""
    base = parent_path if parent_path else "/"
    if not base.endswith("/"):
        base += "/"
    return f"{base}{category_id}/"


def child_depth(parent_depth: int | None) -> int:
    return 0 if parent_depth is None else int(parent_depth) + 1


def is_descendant_of(path: str, ancestor_id: str) -> bool:
    """True si ``path`` pertenece al subárbol de ``ancestor_id`` (incluido él mismo)."""
    return f"/{ancestor_id}/" in (path or "")


def ensure_within_depth(depth: int) -> None:
    if depth > MAX_DEPTH:
        raise CategoryDepthExceededError(
            f"La categoría excede la profundidad máxima permitida ({MAX_DEPTH})")


def ensure_acyclic_reparent(*, category_id: str, category_path: str,
                            new_parent_id: str | None,
                            new_parent_path: str | None) -> None:
    """Impide colocar una categoría bajo sí misma o bajo uno de sus descendientes."""
    if new_parent_id is None:
        return
    if new_parent_id == category_id:
        raise CategoryCycleDetectedError(
            "Una categoría no puede ser su propio padre")
    if new_parent_path and is_descendant_of(new_parent_path, category_id):
        raise CategoryCycleDetectedError(
            "No se puede mover una categoría dentro de su propio subárbol")
