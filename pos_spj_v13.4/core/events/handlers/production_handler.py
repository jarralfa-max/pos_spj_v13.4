# core/events/handlers/production_handler.py
"""
Handler for PRODUCCION_COMPLETADA event - Production inventory updates.

This handler processes production completion events to:
1. Deduct raw materials (source product consumption)
2. Add finished goods (subproducts generation)

Decoupling rule: Uses inventory_service interface via process_movement(),
no direct DB access.
"""
import logging

logger = logging.getLogger(__name__)


def handle_production_completion(event_data: dict, inventory_service) -> None:
    """
    Process inventory movements for completed production batch.

    Args:
        event_data: Event payload containing:
            - batch_id: Production batch ID
            - folio: Batch folio
            - branch_id: Branch/sucursal ID
            - source_product_id: Raw material product ID
            - source_weight: Weight of raw material consumed
            - source_cost_total: Total cost of raw material
            - outputs: List of subproducts with:
                - product_id: Subproduct ID
                - real_weight: Actual weight produced
                - is_waste: Whether this is waste/byproduct
        inventory_service: Service instance with process_movement method

    Handles:
        - Raw material deduction (negative movement)
        - Finished goods addition (positive movement)
        - Waste tracking
    """
    branch_id = event_data.get("branch_id")
    batch_id = event_data.get("batch_id")
    folio = event_data.get("folio", "")
    
    # Source product (raw material)
    src_prod_id = event_data.get("source_product_id")
    src_weight = event_data.get("source_weight", 0)
    
    # Outputs (finished goods + waste)
    outputs = event_data.get("outputs", [])
    
    if not src_prod_id or not src_weight:
        logger.warning(
            "PRODUCCION_COMPLETADA event missing source data - batch_id=%s", 
            batch_id
        )
        return
    
    if not hasattr(inventory_service, 'process_movement'):
        logger.warning("Inventory service does not have process_movement method")
        return
    
    # ── 1. Consumir materia prima ───────────────────────────────────────
    try:
        inventory_service.process_movement(
            product_id=src_prod_id,
            branch_id=branch_id,
            quantity=-float(src_weight),  # negative for consumption
            movement_type="PRODUCCION_CONSUMO",
            reference_id=batch_id,
            reference_type="PRODUCTION_BATCH",
            metadata={
                "folio": folio,
                "movement_purpose": "Raw material consumption for production batch"
            }
        )
        logger.info(
            "Producción: materia prima consumida - batch=%s producto=%s peso=%.3f",
            batch_id[:8], src_prod_id, src_weight
        )
    except Exception as e:
        logger.error(
            "Error consuming raw material for batch %s: %s",
            batch_id[:8], e
        )
        raise
    
    # ── 2. Generar subproductos ─────────────────────────────────────────
    for output in outputs:
        try:
            prod_id = output.get("product_id")
            weight = output.get("real_weight", 0)
            is_waste = output.get("is_waste", False)
            
            if weight <= 0:
                continue
            
            movement_type = "PRODUCCION_MERMA" if is_waste else "PRODUCCION_GENERACION"
            
            inventory_service.process_movement(
                product_id=prod_id,
                branch_id=branch_id,
                quantity=+float(weight),  # positive for generation
                movement_type=movement_type,
                reference_id=batch_id,
                reference_type="PRODUCTION_BATCH",
                metadata={
                    "folio": folio,
                    "is_waste": is_waste,
                    "expected_pct": output.get("expected_pct", 0),
                    "real_pct": output.get("real_pct", 0),
                    "variance_pct": output.get("variance_pct", 0),
                    "cost_allocated": output.get("cost_allocated", 0),
                    "movement_purpose": f"{'Waste' if is_waste else 'Finished good'} from production batch"
                }
            )
            logger.info(
                "Producción: %s generado - batch=%s producto=%s peso=%.3f",
                "Merma" if is_waste else "Subproducto",
                batch_id[:8], prod_id, weight
            )
        except Exception as e:
            logger.error(
                "Error generating output %s for batch %s: %s",
                output.get("product_id"), batch_id[:8], e
            )
            raise
