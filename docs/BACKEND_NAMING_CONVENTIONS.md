# Backend Naming Conventions (WhatsApp + Delivery + Sales)

## Scope
Este documento define las reglas de nombres para la refactorización WhatsApp → Ventas → Delivery → Notificaciones → Forecast → Cotizaciones.

## Mandatory language policy
- **Backend interno (services, DTOs, mappers, methods, internal payloads): English**.
- **Frontend visible (PyQt labels/buttons/dialogs/messages): Spanish**.
- **Legacy DB schema can stay in Spanish**.

## Compatibility rules
1. No renombrar columnas legacy existentes en tablas productivas.
2. La capa de dominio y servicios debe operar con contratos en inglés.
3. Toda traducción entre legacy y dominio debe pasar por mappers explícitos.
4. Estados legacy y estados internos deben mapearse de forma bidireccional.

## Canonical internal keys (English)
- `branch_id`
- `customer_id`
- `product_id`
- `sale_id`
- `order_id`
- `delivery_type`
- `workflow_type`
- `scheduled_at`
- `status`
- `quantity`
- `unit_price`
- `subtotal`
- `created_at`

## Legacy Spanish → Domain English mapping table
- `sucursal_id` → `branch_id`
- `cliente_id` → `customer_id`
- `producto_id` → `product_id`
- `venta_id` → `sale_id`
- `estado` → `status`
- `cantidad` → `quantity`
- `precio_unitario` → `unit_price`
- `direccion_entrega` → `delivery_address`
- `tipo_entrega` → `delivery_type`
- `fecha_entrega_programada` → `scheduled_at`

## Canonical event naming (English)
- `WHATSAPP_ORDER_CREATED`
- `WHATSAPP_SCHEDULED_ORDER_CREATED`
- `WHATSAPP_QUOTE_CREATED`
- `WHATSAPP_QUOTE_ACCEPTED`
- `WHATSAPP_QUOTE_CONVERTED_TO_SALE`
- `FORECAST_DEMAND_UPDATED`
- `BRANCH_NOTIFICATION_CREATED`
- `DELIVERY_ADJUSTMENT_APPROVAL_REQUIRED`
- `DELIVERY_ADJUSTMENT_ACCEPTED`
- `DELIVERY_ADJUSTMENT_REJECTED`
