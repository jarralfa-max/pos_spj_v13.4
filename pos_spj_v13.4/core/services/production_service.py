
# core/services/production_service.py — REPLACED
# This file previously referenced recipe_yields and production_history
# which don't exist in the schema. All production now goes through RecipeEngine.

import logging
logger = logging.getLogger(__name__)


class ProductionService:
    """
    Thin adapter — delegates to RecipeEngine.
    Kept for backward compatibility with any code that still references this class.
    """

    def __init__(self, db_conn, inventory_service):
        self.db = db_conn
        self.inventory_service = inventory_service  # kept for compat, not used

    def execute_production(self, recipe_id: int, input_qty: float,
                           branch_id: int, user_id: str,
                           actual_waste: float = None,
                           mediciones_reales: dict = None) -> dict:
        """Delegates to RecipeEngine.ejecutar_produccion."""
        from core.services.recipe_engine import RecipeEngine, RecipeEngineError
        engine = RecipeEngine(self.db, branch_id=branch_id)
        try:
            result = engine.ejecutar_produccion(
                receta_id=recipe_id,
                cantidad_base=input_qty,
                usuario=str(user_id),
                sucursal_id=branch_id,
                mediciones_reales=mediciones_reales,
            )
            return {
                "folio":              result.operation_id,
                "produccion_id":      result.produccion_id,
                "productos_generados": [
                    {"nombre": c.nombre, "cantidad": c.cantidad}
                    for c in result.componentes if c.tipo == "entrada"
                ],
            }
        except RecipeEngineError as e:
            raise RuntimeError(str(e)) from e
