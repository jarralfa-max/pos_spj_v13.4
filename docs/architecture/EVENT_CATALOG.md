# Event Catalog

## Purpose

Critical mutations must emit domain events so modules can stay interconnected without duplicating business routes.

## Required event payload contract

Every critical event must include:

```text
event_id
event_name
operation_id
entity_id
branch_id
user_id or user_name
timestamp
source_module
payload
```

## Event naming

Event names must be English, uppercase, and stable for integrations.

## Minimum event catalog

```text
SALE_COMPLETED
SALE_CANCELLED
SALE_REFUNDED
CUSTOMER_CREATED
CUSTOMER_UPDATED
CUSTOMER_CREDIT_LIMIT_CHANGED
PRODUCT_CREATED
PRODUCT_UPDATED
PRODUCT_PRICE_CHANGED
INVENTORY_MOVEMENT_RECORDED
INVENTORY_STOCK_LOW
INVENTORY_RESERVED
INVENTORY_RELEASED
WASTE_REGISTERED
WASTE_HIGH_VALUE_REGISTERED
MEAT_PRODUCTION_COMPLETED
MEAT_YIELD_VARIANCE_DETECTED
TRANSFER_DISPATCHED
TRANSFER_RECEIVED
TRANSFER_DIFFERENCE_DETECTED
DELIVERY_ORDER_CREATED
DELIVERY_DRIVER_ASSIGNED
DELIVERY_WEIGHT_ADJUSTED
DELIVERY_ORDER_DELIVERED
QUOTE_CREATED
QUOTE_APPROVED
QUOTE_CONVERTED_TO_SALE
LOYALTY_POINTS_EARNED
LOYALTY_POINTS_REDEEMED
LOYALTY_CARD_ASSIGNED
PURCHASE_PLAN_GENERATED
PURCHASE_ORDER_CREATED
PURCHASE_RECEIVED
CASH_SHIFT_OPENED
CASH_MOVEMENT_RECORDED
CASH_Z_CUT_GENERATED
CASH_DIFFERENCE_DETECTED
ASSET_CREATED
MAINTENANCE_SCHEDULED
MAINTENANCE_COMPLETED
NOTIFICATION_REQUESTED
TICKET_PRINT_REQUESTED
```

## Event routing

Use cases and application services emit events after completing critical mutations. Event handlers connect sales, inventory, cash register, finance, loyalty, delivery, WhatsApp, business intelligence, purchases, production, waste, transfers, tickets, and notifications.

## Operation correlation

`operation_id` is mandatory for critical mutations. It links user action, database changes, events, logs, tickets, and downstream handlers.
