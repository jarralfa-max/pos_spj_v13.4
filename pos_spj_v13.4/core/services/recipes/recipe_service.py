# core/services/recipes/recipe_service.py — FASE 3
"""
Application-layer service for recipe management.

Sits between UI and RecetaRepository:
  UI → RecipeService → RecetaRepository → DB

Responsibilities:
  - Load product lists for UI combo boxes
  - Load recipe + components for edit dialog
  - Delegate create/update/deactivate to RecetaRepository
    (which already enforces tipo_receta ↔ tipo_producto via RecipeValidationService)
  - No direct SQL — all DB access through the repository
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("spj.services.recipes")


class RecipeService:
    """
    Instantiate once per request (thin stateless wrapper).

    Usage::

        svc = RecipeService(db_conn)
        all_recipes = svc.get_all_recipes()
        rid = svc.create_recipe(nombre, product_id, tipo_receta, components, user)
    """

    def __init__(self, db):
        from core.db.connection import wrap
        self._db = wrap(db)
        from repositories.recetas import RecetaRepository
        self._repo = RecetaRepository(db)

    @staticmethod
    def _publish(evento: str, payload: dict) -> None:
        """Emite un evento de receta (best-effort). Remediación E: la UI de
        producción se refresca en caliente con RECETA_CREADA/RECETA_ACTUALIZADA."""
        try:
            from core.events.event_bus import get_bus
            get_bus().publish(evento, payload)
        except Exception:
            pass

    # ── Queries ───────────────────────────────────────────────────────────────

    def get_all_recipes(self, include_inactive: bool = False) -> List[Dict]:
        return self._repo.get_all(include_inactive=include_inactive)

    def get_recipe_by_id(self, receta_id: int) -> Optional[Dict]:
        return self._repo.get_by_id(receta_id)

    def get_recipe_components(self, receta_id: int) -> List[Dict]:
        return self._repo.get_components(receta_id)

    def get_recipe_for_product(self, product_id: int) -> Optional[Dict]:
        return self._repo.get_for_product(product_id)

    def get_recipe_data_for_edit(self, receta_id: int) -> Tuple[Optional[Dict], List[Dict]]:
        """Return (receta_dict, componentes_list) ready to populate the edit dialog."""
        receta = self._repo.get_by_id(receta_id)
        if not receta:
            return None, []
        componentes = self._repo.get_components(receta_id)
        return receta, componentes

    def get_products_for_ui(self) -> List[Dict]:
        """List of active products for combo boxes in recipe dialogs."""
        rows = self._db.execute(
            "SELECT id, nombre, unidad FROM productos WHERE activo=1 ORDER BY nombre"
        ).fetchall()
        return [
            {"id": r[0] if not hasattr(r, "keys") else r["id"],
             "nombre": r[1] if not hasattr(r, "keys") else r["nombre"],
             "unidad": (r[2] if not hasattr(r, "keys") else r["unidad"]) or "kg"}
            for r in rows
        ]

    # ── Commands ──────────────────────────────────────────────────────────────

    def create_recipe(
        self,
        nombre: str,
        base_product_id: int,
        components: List[Dict],
        usuario: str,
        tipo_receta: str = "SUBPRODUCTO",
    ) -> int:
        """
        Create a recipe. Raises RecetaError (or subclass) on validation failure.
        Returns the new receta_id.
        """
        logger.info(
            "create_recipe product=%s tipo=%s components=%d user=%s",
            base_product_id, tipo_receta, len(components), usuario,
        )
        receta_id = self._repo.create(
            nombre=nombre,
            base_product_id=base_product_id,
            components=components,
            usuario=usuario,
            tipo_receta=tipo_receta,
        )
        self._publish("RECETA_CREADA", {
            "receta_id": receta_id, "base_product_id": base_product_id,
            "tipo_receta": tipo_receta, "usuario": usuario,
        })
        return receta_id

    def update_recipe(
        self,
        receta_id: int,
        nombre: str,
        components: List[Dict],
        usuario: str,
    ) -> None:
        """Update recipe name and components. Raises RecetaError on failure."""
        logger.info("update_recipe id=%s user=%s", receta_id, usuario)
        self._repo.update(receta_id, nombre, components, usuario)
        self._publish("RECETA_ACTUALIZADA", {"receta_id": receta_id, "usuario": usuario})

    def deactivate_recipe(self, receta_id: int, usuario: str) -> None:
        """Soft-delete a recipe. Clears dependency graph entries."""
        logger.info("deactivate_recipe id=%s user=%s", receta_id, usuario)
        self._repo.deactivate(receta_id, usuario)
        self._publish("RECETA_ACTUALIZADA", {"receta_id": receta_id, "usuario": usuario,
                                             "estado": "inactiva"})
