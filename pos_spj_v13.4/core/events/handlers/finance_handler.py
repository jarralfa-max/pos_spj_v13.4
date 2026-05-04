# core/events/handlers/finance_handler.py
"""
Handler for VENTA_COMPLETADA event - Finance registration.

This handler is responsible for registering income when a sale is completed.
It handles cash and card payments (not credit sales - those create accounts receivable).

Decoupling rule: Uses finance_service interface, no direct DB access.
"""
import logging

logger = logging.getLogger(__name__)


def handle_sale_finance(event_data: dict, finance_service) -> None:
    """
    Register income for a completed sale (cash/card payments only).
    
    Args:
        event_data: Event payload containing:
            - venta_id: Sale ID
            - folio: Sale folio
            - branch_id: Branch/sucursal ID
            - total: Total amount of the sale
            - usuario: User who processed the sale
            - operation_id: Unique operation identifier
            - payment_method: Payment method (Efectivo, Tarjeta, etc.)
            - cliente_id: Optional customer ID
        finance_service: Service instance with register_income method
    
    Handles:
        - Cash payments: Register as immediate income
        - Card payments: Register as immediate income
        - Credit sales: SKIP (handled by customer service for accounts receivable)
    """
    branch_id = event_data.get("branch_id")
    user = event_data.get("usuario", "sistema")
    folio = event_data.get("folio", "")
    sale_id = event_data.get("venta_id")
    operation_id = event_data.get("operation_id", "")
    total = float(event_data.get("total", 0))
    payment_method = event_data.get("payment_method", "")
    client_id = event_data.get("cliente_id")
    
    # Skip if no amount to register
    if total <= 0:
        return
    
    # Skip credit sales - these create accounts receivable, not immediate income
    # Credit sales are handled separately by customer service
    if payment_method == "Credito":
        logger.debug("Credit sale %s - skipping immediate income registration", sale_id)
        return
    
    if not hasattr(finance_service, 'register_income'):
        logger.warning("Finance service does not have register_income method")
        return
    
    try:
        finance_service.register_income(
            amount=total,
            category="VENTAS_MOSTRADOR",
            description=f"Ingreso por venta {folio}",
            payment_method=payment_method,
            branch_id=branch_id,
            user=user,
            operation_id=operation_id,
            reference_id=sale_id
        )
        logger.debug("Income registered for sale %s: $%.2f via %s", sale_id, total, payment_method)
        
    except Exception as e:
        logger.error("Error registering income for sale %s: %s", sale_id, e)
        # Don't re-raise - sale is already complete, this is a side-effect


def handle_credit_sale(event_data: dict, customer_service, finance_service) -> None:
    """
    Handle credit sale - create accounts receivable entry.
    
    This handler is called for credit sales to:
    1. Create an accounts receivable (CxC) entry
    2. Link it to the customer and sale
    3. Deduct from customer's available credit
    
    Args:
        event_data: Event payload containing:
            - venta_id: Sale ID
            - folio: Sale folio
            - total: Total amount of the sale
            - cliente_id: Customer ID (required for credit sales)
            - branch_id: Branch ID
            - usuario: User who processed the sale
        customer_service: Service with credit management methods
        finance_service: Service with accounts receivable methods
    """
    sale_id = event_data.get("venta_id")
    folio = event_data.get("folio", "")
    total = float(event_data.get("total", 0))
    client_id = event_data.get("cliente_id")
    branch_id = event_data.get("branch_id")
    user = event_data.get("usuario", "sistema")
    
    if not client_id:
        logger.error("Credit sale %s has no customer_id - cannot create CxC", sale_id)
        return
    
    if total <= 0:
        return
    
    # Register accounts receivable
    try:
        if finance_service and hasattr(finance_service, 'register_accounts_receivable'):
            finance_service.register_accounts_receivable(
                customer_id=client_id,
                sale_id=sale_id,
                amount=total,
                branch_id=branch_id,
                user=user,
                description=f"Venta a crédito {folio}"
            )
            logger.info("Accounts receivable created for credit sale %s - customer %s, amount $%.2f",
                       sale_id, client_id, total)
        
        # Deduct from customer's available credit
        if customer_service and hasattr(customer_service, 'deduct_credit'):
            customer_service.deduct_credit(
                customer_id=client_id,
                amount=total,
                reference_type="VENTA_CREDITO",
                reference_id=str(sale_id),
                user=user
            )
            logger.debug("Credit deducted for customer %s: $%.2f", client_id, total)
            
    except Exception as e:
        logger.error("Error processing credit sale %s: %s", sale_id, e)
        # Note: This could be critical - may need to flag for manual review
