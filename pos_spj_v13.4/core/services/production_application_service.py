# core/services/production_application_service.py — FASE 7
"""
ProductionApplicationService — single application-layer entry point for all
production operations in the SPJ ERP.

Unifies two previously parallel engines:
  RecipeEngine  (core/services/recipe_engine.py)
    → recipe-based single-step execution: subproducto, combinacion, produccion
    → preview, historial, detalle
  ProductionEngine  (core/production/production_engine.py)
    → industrial batch lifecycle: open → add outputs → close
  GestionarProduccionUC  (core/use_cases/produccion.py)
    → orchestration: open_batch + close_batch + EventBus

This service is a pure delegation layer — no business logic lives here.
All domain decisions remain in RecipeEngine / ProductionEngine / GestionarProduccionUC.

Registered by AppContainer as `container.produccion_service`.

Usage from UI (modulos/produccion.py):
    svc = container.produccion_service

    # Simple recipe execution
    result = svc.ejecutar_receta(receta_id=5, cantidad_base=20.0,
                                  usuario="juan", sucursal_id=1)

    # Industrial batch
    r = svc.abrir_lote(producto_origen_id=1, peso_kg=100.0,
                        sucursal_id=1, usuario="juan")
    svc.agregar_subproducto(batch_id=r.batch_id, producto_id=2,
                            peso_kg=60.0)
    r2 = svc.cerrar_lote(batch_id=r.batch_id,
                          sucursal_id=1, usuario="juan")
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("spj.services.produccion")


class ProductionApplicationService:
    """
    Orchestration facade for all production flows.

    Args:
        recipe_engine:     RecipeEngine instance (recipe-based execution).
        production_uc:     GestionarProduccionUC instance (batch lifecycle + events).
        production_engine: ProductionEngine instance (batch detail operations).
                           Optional — some call sites only need recipe execution.
    """

    def __init__(
        self,
        recipe_engine,
        production_uc,
        production_engine=None,
    ):
        self._recipe   = recipe_engine
        self._uc       = production_uc
        self._engine   = production_engine

    @classmethod
    def from_container(cls, container) -> "ProductionApplicationService":
        """
        Construct from an AppContainer.

        Requires container.recipe_engine and container.uc_produccion to exist.
        container.production_engine is optional but used for batch detail ops.
        """
        return cls(
            recipe_engine    = container.recipe_engine,
            production_uc    = container.uc_produccion,
            production_engine= getattr(container, "production_engine", None),
        )

    # ── Unified dispatcher ────────────────────────────────────────────────────

    def ejecutar_produccion(
        self,
        receta_id: int,
        cantidad_base: float,
        usuario: str,
        sucursal_id: Optional[int] = None,
        notas: str = "",
        operation_id: Optional[str] = None,
        mediciones_reales: Optional[Dict[int, float]] = None,
    ):
        """
        Unified production entry point — routes to the appropriate engine.

        Dispatch rules:
          recipe types subproducto / combinacion / produccion
            → RecipeEngine.ejecutar_produccion()  (formula-based, single step)
          batch-based industrial flow
            → use the explicit batch methods (abrir_lote / cerrar_lote)

        All three recipe types currently route to RecipeEngine.  The batch
        workflow (open → add outputs → close) requires explicit multi-step
        calls and is not collapsible into a single dispatch because output
        weights are measured on a physical scale between steps.

        Returns ProduccionResultDTO.
        """
        logger.info(
            "ejecutar_produccion: receta=%s cantidad=%.4f usuario=%s suc=%s",
            receta_id, cantidad_base, usuario, sucursal_id,
        )
        return self._recipe.ejecutar_produccion(
            receta_id         = receta_id,
            cantidad_base     = cantidad_base,
            usuario           = usuario,
            sucursal_id       = sucursal_id,
            notas             = notas,
            operation_id      = operation_id,
            mediciones_reales = mediciones_reales,
        )

    # ── Recipe-based production ───────────────────────────────────────────────

    def ejecutar_receta(
        self,
        receta_id: int,
        cantidad_base: float,
        usuario: str,
        sucursal_id: Optional[int] = None,
        notas: str = "",
        operation_id: Optional[str] = None,
        mediciones_reales: Optional[Dict[int, float]] = None,
    ):
        """
        Execute a single-step recipe production.

        Delegates to RecipeEngine.ejecutar_produccion().
        Returns ProduccionResultDTO.

        Raises:
            RecetaNoEncontradaError  — recipe not found or inactive.
            StockInsuficienteProduccionError — insufficient component stock.
            ProduccionDuplicadaError — duplicate operation_id.
            RecipeEngineError — any other engine-level failure.
        """
        return self._recipe.ejecutar_produccion(
            receta_id        = receta_id,
            cantidad_base    = cantidad_base,
            usuario          = usuario,
            sucursal_id      = sucursal_id,
            notas            = notas,
            operation_id     = operation_id,
            mediciones_reales= mediciones_reales,
        )

    def preview_receta(self, receta_id: int, cantidad_base: float) -> List[Dict]:
        """
        Return the inventory movements that would be applied for a recipe
        execution, without committing anything.

        Delegates to RecipeEngine.preview_produccion().
        """
        return self._recipe.preview_produccion(receta_id, cantidad_base)

    def get_historial(
        self,
        sucursal_id: Optional[int] = None,
        receta_id: Optional[int] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Production history from the `producciones` table."""
        return self._recipe.get_historial(
            sucursal_id=sucursal_id,
            receta_id=receta_id,
            limit=limit,
        )

    def get_detalle(self, produccion_id: int) -> List[Dict]:
        """Line-level detail for one production record."""
        return self._recipe.get_detalle_produccion(produccion_id)

    # ── Industrial batch lifecycle ────────────────────────────────────────────

    def abrir_lote(
        self,
        producto_origen_id: int,
        peso_kg: float,
        sucursal_id: int,
        usuario: str,
        receta_id: Optional[int] = None,
    ):
        """
        Open a new production batch.

        Delegates to GestionarProduccionUC.abrir_lote().
        Returns ResultadoProduccion.
        """
        if self._uc is None:
            raise RuntimeError(
                "ProductionApplicationService: uc_produccion not available — "
                "check container initialization."
            )
        return self._uc.abrir_lote(
            producto_origen_id = producto_origen_id,
            peso_kg            = peso_kg,
            sucursal_id        = sucursal_id,
            usuario            = usuario,
            receta_id          = receta_id,
        )

    def agregar_subproducto(
        self,
        batch_id: str,
        producto_id: int,
        peso_kg: float,
        expected_pct: float = 0.0,
        is_waste: bool = False,
    ):
        """
        Add an output (sub-product or waste) to an open batch.

        Delegates to ProductionEngine.add_output().
        Returns OutputDTO.
        """
        if self._engine is None:
            raise RuntimeError(
                "ProductionApplicationService: production_engine not available — "
                "check container initialization."
            )
        return self._engine.add_output(
            batch_id     = batch_id,
            product_id   = producto_id,
            weight       = peso_kg,
            expected_pct = expected_pct,
            is_waste     = is_waste,
        )

    def remover_subproducto(self, batch_id: str, producto_id: int) -> None:
        """Remove an output from an open batch."""
        if self._engine is None:
            raise RuntimeError("production_engine not available")
        self._engine.remove_output(batch_id=batch_id, product_id=producto_id)

    def cerrar_lote(
        self,
        batch_id: str,
        sucursal_id: int,
        usuario: str,
    ):
        """
        Close a batch: validate weight balance, apply inventory movements,
        distribute costs, publish PRODUCCION_COMPLETADA.

        Delegates to GestionarProduccionUC.cerrar_lote().
        Returns ResultadoProduccion.
        """
        if self._uc is None:
            raise RuntimeError("uc_produccion not available")
        return self._uc.cerrar_lote(
            batch_id    = batch_id,
            sucursal_id = sucursal_id,
            usuario     = usuario,
        )

    def cancelar_lote(self, batch_id: str, usuario: str, motivo: str = "") -> None:
        """Cancel an open batch without applying inventory movements."""
        if self._engine is None:
            raise RuntimeError("production_engine not available")
        self._engine.cancel_batch(
            batch_id      = batch_id,
            cancelled_by  = usuario,
            motivo        = motivo,
        )

    def preview_lote(self, batch_id: str):
        """
        Compute the yield analysis for a batch without closing it.

        Delegates to ProductionEngine.preview_batch().
        Returns YieldResult.
        """
        if self._engine is None:
            raise RuntimeError("production_engine not available")
        return self._engine.preview_batch(batch_id)

    def get_batches(
        self,
        branch_id: Optional[int] = None,
        estado: Optional[str] = None,
        fecha_desde: str = "",
        fecha_hasta: str = "",
        limit: int = 100,
    ) -> List[Dict]:
        """Return production batch list from ProductionEngine."""
        if self._engine is None:
            return []
        return self._engine.get_batches(
            branch_id   = branch_id,
            estado      = estado,
            fecha_desde = fecha_desde,
            fecha_hasta = fecha_hasta,
            limit       = limit,
        )

    def get_batch_detail(self, batch_id: str) -> Dict[str, Any]:
        """Return full batch detail including outputs, yield analysis, cost ledger."""
        if self._engine is None:
            return {}
        return self._engine.get_batch_detail(batch_id)
