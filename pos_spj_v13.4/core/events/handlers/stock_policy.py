# core/events/handlers/stock_policy.py
"""
Handlers de políticas de negocio para eventos de inventario.

Estos handlers implementan reglas de negocio que reaccionan a eventos:
- STOCK_LEVEL_CRITICAL → Auto-reorder alerts
- RECIPE_DEVIATION_DETECTED → Quality control alerts
- QUOTE_EXPIRED → Sales follow-up

No realizan mutaciones directas, solo notifican o crean registros de seguimiento.
"""
import logging
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)


def handle_stock_level_critical(event_data: dict, notification_service=None, purchase_service=None) -> None:
    """
    Policy: When stock falls below threshold, trigger alerts and suggest reorder.
    
    Args:
        event_data: {product_id, current_qty, threshold, branch_id}
        notification_service: Service for sending alerts
        purchase_service: Service for creating suggested POs
    """
    product_id = event_data.get("product_id")
    current_qty = event_data.get("current_qty", 0)
    threshold = event_data.get("threshold", 0)
    branch_id = event_data.get("branch_id")
    
    if not all([product_id, branch_id]):
        logger.warning("STOCK_LEVEL_CRITICAL event missing required fields: %s", event_data)
        return
    
    logger.warning(
        "Stock crítico: producto=%s sucursal=%s stock=%.2f mínimo=%.2f",
        product_id, branch_id, current_qty, threshold
    )
    
    # Notificar al servicio de notificaciones
    if notification_service and hasattr(notification_service, 'notificar_stock_bajo'):
        try:
            notification_service.notificar_stock_bajo(
                [{
                    "producto_id": product_id,
                    "stock_actual": current_qty,
                    "stock_minimo": threshold,
                    "sucursal_id": branch_id
                }],
                sucursal_id=branch_id
            )
        except Exception as e:
            logger.error("Error notifying stock critical: %s", e)
    
    # TODO: Crear sugerencia de orden de compra automática
    # if purchase_service and hasattr(purchase_service, 'create_suggested_po'):
    #     purchase_service.create_suggested_po(product_id, branch_id)


def handle_recipe_deviation(event_data: dict, quality_service=None) -> None:
    """
    Policy: When production yield variance exceeds threshold, alert quality control.
    
    Args:
        event_data: {order_id, variance_pct, missing_ingredients[], severity}
        quality_service: Service for quality tracking
    """
    order_id = event_data.get("order_id")
    variance_pct = event_data.get("variance_pct", 0)
    severity = event_data.get("severity", "medium")
    branch_id = event_data.get("branch_id")
    
    if not order_id:
        logger.warning("RECIPE_DEVIATION_DETECTED event missing order_id: %s", event_data)
        return
    
    logger.warning(
        "Desviación en producción: orden=%s variación=%.2f%% severidad=%s",
        order_id, variance_pct, severity
    )
    
    # Alertar si la severidad es alta
    if severity in ("high", "critical") and quality_service:
        try:
            if hasattr(quality_service, 'record_deviation'):
                quality_service.record_deviation(
                    order_id=order_id,
                    variance_pct=variance_pct,
                    severity=severity,
                    branch_id=branch_id
                )
        except Exception as e:
            logger.error("Error recording recipe deviation: %s", e)


def handle_quote_expired(event_data: dict, crm_service=None) -> None:
    """
    Policy: When quote expires, trigger sales follow-up workflow.
    
    Args:
        event_data: {quote_id, customer_id, total, days_since_creation}
        crm_service: Service for CRM/follow-up
    """
    quote_id = event_data.get("quote_id")
    customer_id = event_data.get("customer_id")
    total = event_data.get("total", 0)
    
    if not quote_id:
        logger.warning("QUOTE_EXPIRED event missing quote_id: %s", event_data)
        return
    
    logger.info("Cotización expirada: quote=%s cliente=%s total=$%.2f", 
                quote_id, customer_id, total)
    
    # Trigger follow-up task in CRM
    if crm_service and hasattr(crm_service, 'create_follow_up'):
        try:
            crm_service.create_follow_up(
                customer_id=customer_id,
                quote_id=quote_id,
                reason="quote_expired",
                priority="medium"
            )
        except Exception as e:
            logger.error("Error creating quote follow-up: %s", e)
