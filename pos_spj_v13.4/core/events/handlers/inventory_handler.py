# core/events/handlers/inventory_handler.py
"""
Handler for VENTA_COMPLETADA event - Inventory deduction.

This handler is responsible for deducting inventory when a sale is completed.
It handles both simple items and composite items (combos with recipes).

Decoupling rule: Uses inventory_service interface, no direct DB access.
"""
import logging

logger = logging.getLogger(__name__)


def handle_sale_inventory(event_data: dict, inventory_service) -> None:
    """
    Deduct inventory for all items in a completed sale.
    
    Args:
        event_data: Event payload containing:
            - venta_id: Sale ID
            - folio: Sale folio
            - branch_id: Branch/sucursal ID
            - usuario: User who processed the sale
            - operation_id: Unique operation identifier
            - items: List of items with product_id, qty, es_compuesto
        inventory_service: Service instance with deduct_stock method
    
    Handles:
        - Simple items: Direct stock deduction
        - Composite items (combos): Recipe-based ingredient deduction
    """
    branch_id = event_data.get("branch_id")
    user = event_data.get("usuario", "sistema")
    folio = event_data.get("folio", "")
    sale_id = event_data.get("venta_id")
    operation_id = event_data.get("operation_id", "")
    items = event_data.get("items", [])
    
    if not items:
        logger.warning("VENTA_COMPLETADA event missing items payload - venta_id=%s", sale_id)
        return
    
    if not hasattr(inventory_service, 'deduct_stock'):
        logger.warning("Inventory service does not have deduct_stock method")
        return
    
    for item in items:
        try:
            product_id = item.get('product_id') or item.get('producto_id')
            qty = float(item.get('qty') or item.get('cantidad') or 1)
            es_compuesto = item.get('es_compuesto', 0)
            
            if es_compuesto == 1:
                # Composite item: deduct ingredients from recipe
                _deduct_combo_ingredients(
                    inventory_service=inventory_service,
                    product_id=product_id,
                    sale_qty=qty,
                    branch_id=branch_id,
                    operation_id=operation_id,
                    sale_id=sale_id,
                    folio=folio,
                    user=user
                )
            else:
                # Simple item: direct stock deduction via process_movement
                inventory_service.process_movement(
                    product_id=product_id,
                    quantity=-qty,  # negative for outbound
                    movement_type="sale",
                    reference_id=str(sale_id),
                    branch_id=branch_id,
                    metadata={"notes": f"Salida por venta {folio}"}
                )
                
        except Exception as e:
            logger.error("Error deducting inventory for item %s in sale %s: %s", 
                        item.get('product_id'), sale_id, e)
            # Continue with other items - don't fail entire sale


def _deduct_combo_ingredients(
    inventory_service,
    product_id: int,
    sale_qty: float,
    branch_id: int,
    operation_id: str,
    sale_id: int,
    folio: str,
    user: str
) -> None:
    """
    Deduct ingredients for a combo/composite product based on its recipe.
    
    This function retrieves the recipe for the combo and deducts each
    ingredient proportionally based on the quantity sold.
    
    Args:
        inventory_service: Service with deduct_stock method
        product_id: The combo product ID
        sale_qty: Quantity of combos sold
        branch_id: Branch ID
        operation_id: Operation identifier
        sale_id: Sale ID for reference
        folio: Sale folio for notes
        user: User processing the sale
    """
    # Get recipe repository from inventory service or use direct DB access
    # Note: This requires the inventory_service to have access to recipe_repo
    recipe_repo = getattr(inventory_service, 'recipe_repo', None)
    db_conn = getattr(inventory_service, 'db', None)
    
    if not recipe_repo and not db_conn:
        logger.warning("Cannot deduct combo ingredients: no recipe access for product %s", product_id)
        return
    
    # Fetch recipe items
    recipe_items = []
    if recipe_repo and hasattr(recipe_repo, 'get_recipe_items_by_product'):
        recipe_items = recipe_repo.get_recipe_items_by_product(product_id)
    elif db_conn:
        # Fallback: direct DB query
        cursor = db_conn.execute(
            "SELECT component_product_id, cantidad, tipo_receta, rendimiento_pct "
            "FROM recetas WHERE producto_id=?",
            (product_id,)
        )
        rows = cursor.fetchall()
        if rows:
            recipe_items = [
                {
                    'component_product_id': row[0],
                    'cantidad': row[1],
                    'tipo_receta': row[2] or 'combinacion',
                    'rendimiento_pct': row[3]
                }
                for row in rows
            ]
    
    if not recipe_items:
        logger.warning("Combo product %s has no recipe defined", product_id)
        return
    
    for sub_item in recipe_items:
        try:
            tipo_receta = sub_item.get('tipo_receta', 'combinacion')
            rend_pct = float(sub_item.get('rendimiento_pct') or 0)
            cantidad = float(sub_item.get('cantidad') or 0)
            
            if rend_pct > 0:
                # Percentage-based (subproducto type)
                qty_to_deduct = sale_qty * rend_pct / 100.0
            elif cantidad > 0:
                # Fixed-quantity (combinacion type)
                qty_to_deduct = sale_qty * cantidad
            else:
                logger.warning("Recipe component pid=%s has no qty/rendimiento — skipped",
                              sub_item['component_product_id'])
                continue
            
            if qty_to_deduct <= 0:
                continue
            
            inventory_service.process_movement(
                product_id=sub_item['component_product_id'],
                quantity=-round(qty_to_deduct, 4),  # negative for outbound
                movement_type="sale",
                reference_id=str(sale_id),
                branch_id=branch_id,
                metadata={"notes": f"Consumo receta {folio} ({tipo_receta})"}
            )
            
        except Exception as e:
            logger.error("Error deducting ingredient %s for combo %s: %s",
                        sub_item.get('component_product_id'), product_id, e)
            # Continue with other ingredients


def handle_stock_transfer(event_data: dict, inventory_service) -> None:
    """
    Process stock transfer between branches.
    
    Args:
        event_data: Event payload containing:
            - producto_id: Product ID
            - cantidad: Quantity to transfer
            - sucursal_origen: Origin branch ID
            - sucursal_destino: Destination branch ID
            - usuario: User who initiated transfer
            - notas: Optional notes
            - op_id: Operation identifier
        inventory_service: Service with process_movement method
    """
    product_id = event_data.get("producto_id")
    quantity = event_data.get("cantidad")
    origin_branch = event_data.get("sucursal_origen")
    dest_branch = event_data.get("sucursal_destino")
    user = event_data.get("usuario", "sistema")
    notes = event_data.get("notas", "")
    op_id = event_data.get("op_id", "")

    if not all([product_id, quantity, origin_branch, dest_branch]):
        logger.warning("TRANSFERENCIA_STOCK event missing required fields: %s", event_data)
        return

    try:
        # Deduct from origin branch (negative quantity)
        inventory_service.process_movement(
            product_id=product_id,
            quantity=-quantity,
            movement_type="transfer",
            reference_id=str(op_id),
            branch_id=origin_branch,
            metadata={
                "notes": f"Traspaso salida: {notes}",
                "transfer_type": "outbound",
                "destination_branch_id": dest_branch
            }
        )
        
        # Add to destination branch (positive quantity)
        inventory_service.process_movement(
            product_id=product_id,
            quantity=quantity,
            movement_type="transfer",
            reference_id=str(op_id),
            branch_id=dest_branch,
            metadata={
                "notes": f"Traspaso entrada: {notes}",
                "transfer_type": "inbound",
                "origin_branch_id": origin_branch
            }
        )
        
        logger.info("Transfer completed: product=%s qty=%s from %s to %s (op=%s)",
                   product_id, quantity, origin_branch, dest_branch, op_id)
                   
    except Exception as e:
        logger.error("Error processing transfer for product %s: %s", product_id, e)
        raise  # Re-raise to trigger rollback in transactional context
