# core/use_cases/produccion.py — SPJ POS v13.3
"""
Caso de uso: Gestionar Producción Cárnica

Orquesta el flujo completo de un lote de producción:
  1. Abrir lote (crear batch con materia prima)
  2. Agregar subproductos (outputs parciales)
  3. Cerrar lote:
     a. Validar balance de peso
     b. Consumir materia prima (inventario)
     c. Generar subproductos (inventario)
     d. Distribuir costos
     e. Publicar PRODUCCION_COMPLETADA al EventBus

Relación con módulos existentes:
  - core/production/production_engine.py → motor de cálculo (delegado)
  - modulos/produccion.py → UI (consume este UC)
  - core/services/recipe_engine.py → recetas (consultado)

Este UC NO reemplaza ProductionEngine — lo orquesta.
ProductionEngine ejecuta la lógica de cálculo pura.
Este UC agrega: validación de entrada, eventos, sync, audit.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger("spj.use_cases.produccion")


# ── DTOs ──────────────────────────────────────────────────────────────────────

@dataclass
class SubproductoInput:
    """Input para agregar un subproducto al lote."""
    producto_id: int
    nombre: str
    peso_kg: float
    tipo: str = "corte"  # corte, subproducto, merma


@dataclass
class ResultadoProduccion:
    ok: bool
    batch_id: str = ""
    folio: str = ""
    rendimiento_pct: float = 0.0
    movimientos: int = 0
    error: str = ""


# ── Caso de uso ───────────────────────────────────────────────────────────────

class GestionarProduccionUC:
    """
    Orquestador del flujo de producción cárnica.

    Uso desde UI (modulos/produccion.py):
        uc = container.uc_produccion
        r  = uc.cerrar_lote(batch_id=batch_id, usuario="produccion",
                             sucursal_id=1)

    Uso desde tests:
        uc = GestionarProduccionUC(
            production_engine=mock_engine,
            inventory_service=mock_inv,
            event_bus=mock_bus,
        )
    """

    def __init__(
        self,
        production_engine,
        inventory_service,
        event_bus=None,
    ):
        self._engine = production_engine
        self._inv = inventory_service
        self._bus = event_bus

    @classmethod
    def desde_container(cls, container) -> "GestionarProduccionUC":
        return cls(
            production_engine=container.production_engine,
            inventory_service=container.inventory_service,
            event_bus=_get_bus(),
        )

    # ── Abrir lote ────────────────────────────────────────────────────────────

    def abrir_lote(
        self,
        producto_origen_id: int,
        peso_kg: float,
        sucursal_id: int,
        usuario: str,
        receta_id: Optional[int] = None,
    ) -> ResultadoProduccion:
        """Crea un nuevo lote de producción con la materia prima indicada."""
        if peso_kg <= 0:
            return ResultadoProduccion(ok=False, error="Peso debe ser > 0.")

        try:
            # FIX BUG-3: ProductionEngine expone open_batch(), no create_batch()
            result = self._engine.open_batch(
                product_source_id=producto_origen_id,
                source_weight=peso_kg,
                branch_id=sucursal_id,
                created_by=usuario,
                receta_id=receta_id,
            )
            return ResultadoProduccion(
                ok=True,
                batch_id=result.batch_id,
                folio=result.folio,
            )
        except Exception as e:
            logger.error("abrir_lote: %s", e)
            return ResultadoProduccion(ok=False, error=str(e))

    # ── Cerrar lote ───────────────────────────────────────────────────────────

    def cerrar_lote(
        self,
        batch_id: str,
        sucursal_id: int,
        usuario: str,
    ) -> ResultadoProduccion:
        """
        Cierra el lote: valida balance, mueve inventario, distribuye costos.
        Publica PRODUCCION_COMPLETADA al EventBus.
        """
        operation_id = str(uuid.uuid4())

        try:
            # FIX BUG-5: close_batch espera `closed_by`, no `user`; no tiene `operation_id`
            result = self._engine.close_batch(
                batch_id=batch_id,
                closed_by=usuario,
            )
        except Exception as e:
            logger.error("cerrar_lote engine: %s", e)
            return ResultadoProduccion(ok=False, error=str(e))

        # ── Publicar evento ───────────────────────────────────────────────
        if self._bus:
            try:
                # FIX BUG-4: YieldResult tiene usable_pct, no yield_pct
                rendimiento_pub = (
                    result.yield_result.usable_pct
                    if result.yield_result else 0.0
                )
                self._bus.publish("PRODUCCION_COMPLETADA", {
                    "batch_id": batch_id,
                    "folio": result.folio,
                    "rendimiento_pct": rendimiento_pub,
                    "movimientos": result.inventory_movements,
                    "cost_allocations": result.cost_allocations,
                    "sucursal_id": sucursal_id,
                    "usuario": usuario,
                    "operation_id": operation_id,
                })
            except Exception as e:
                logger.warning("EventBus post-produccion: %s", e)

        # FIX BUG-4: usar usable_pct en lugar del inexistente yield_pct
        rendimiento = (
            result.yield_result.usable_pct
            if result.yield_result else 0.0
        )

        logger.info(
            "Lote %s cerrado — rendimiento=%.1f%% movimientos=%d",
            result.folio, rendimiento, result.inventory_movements,
        )

        return ResultadoProduccion(
            ok=True,
            batch_id=batch_id,
            folio=result.folio,
            rendimiento_pct=rendimiento,
            movimientos=result.inventory_movements,
        )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_bus():
    try:
        from core.events.event_bus import get_bus
        return get_bus()
    except Exception:
        return None
