# core/events/handlers/purchase_handler.py
"""
Handler for COMPRA_REGISTRADA event - Inventory addition.

This handler is responsible for adding inventory when a purchase is completed.
It processes each item in the purchase and registers it via process_movement().

Decoupling rule: Uses inventory_service interface, no direct DB access.
"""
import logging

logger = logging.getLogger(__name__)


def handle_purchase_inventory(event_data: dict, inventory_service) -> None:
    """
    Add inventory for all items in a completed purchase.
    
    Args:
        event_data: Event payload containing:
            - compra_id: Purchase ID
            - folio: Purchase folio
            - branch_id: Branch/sucursal ID
            - user: User who processed the purchase
            - operation_id: Unique operation identifier
            - items: List of items with product_id, qty, unit_cost
            - provider_id: Supplier ID
        inventory_service: Service instance with process_movement method
    
    Handles:
        - Simple items: Direct stock addition via process_movement()
        - Cost tracking: Includes unit_cost in metadata for average cost calculation
    """
    branch_id = event_data.get("branch_id")
    user = event_data.get("user", "sistema")
    folio = event_data.get("folio", "")
    purchase_id = event_data.get("compra_id")
    operation_id = event_data.get("operation_id", "")
    items = event_data.get("items", [])
    provider_id = event_data.get("provider_id")
    
    if not items:
        logger.warning("COMPRA_REGISTRADA event missing items payload - compra_id=%s", purchase_id)
        return
    
    if not hasattr(inventory_service, 'process_movement'):
        logger.warning("Inventory service does not have process_movement method")
        return
    
    for item in items:
        try:
            product_id = item.get('product_id') or item.get('producto_id')
            qty = float(item.get('qty') or item.get('cantidad') or 0)
            unit_cost = float(item.get('unit_cost') or item.get('costo_unitario') or 0)
            
            if qty <= 0:
                logger.warning("Item with invalid qty=%s skipped in purchase %s", qty, purchase_id)
                continue
            
            # Add inventory via process_movement (positive quantity for inbound)
            inventory_service.process_movement(
                product_id=product_id,
                quantity=qty,  # positive for inbound
                movement_type="purchase",
                reference_id=str(purchase_id),
                branch_id=branch_id,
                metadata={
                    "unit_cost": unit_cost,
                    "notes": f"Entrada por compra {folio}",
                    "provider_id": provider_id
                }
            )
            
        except Exception as e:
            logger.error("Error adding inventory for item %s in purchase %s: %s", 
                        item.get('product_id'), purchase_id, e)
            # Continue with other items - don't fail entire purchase
