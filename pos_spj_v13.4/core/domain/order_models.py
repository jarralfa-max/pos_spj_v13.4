from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class OrderWorkflowType(str, Enum):
    COUNTER = "counter"
    DELIVERY = "delivery"
    SCHEDULED = "scheduled"


class DeliveryType(str, Enum):
    PICKUP = "pickup"
    HOME_DELIVERY = "home_delivery"


class OrderStatus(str, Enum):
    SCHEDULED = "scheduled"
    PENDING = "pending"
    PREPARATION = "preparation"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


@dataclass
class OrderItem:
    product_id: Optional[int]
    product_name: str
    quantity: float
    unit_price: float
    subtotal: float
    unit: str = "kg"


@dataclass
class WhatsAppOrder:
    order_id: Optional[int] = None
    sale_id: Optional[int] = None
    branch_id: Optional[int] = None
    customer_id: Optional[int] = None
    customer_name: str = ""
    customer_phone: str = ""
    delivery_address: str = ""
    workflow_type: OrderWorkflowType = OrderWorkflowType.DELIVERY
    delivery_type: DeliveryType = DeliveryType.HOME_DELIVERY
    status: OrderStatus = OrderStatus.PENDING
    scheduled_at: Optional[datetime] = None
    source_channel: str = "whatsapp"
    items: List[OrderItem] = field(default_factory=list)


@dataclass
class QuoteItem(OrderItem):
    pass


@dataclass
class Quote:
    quote_id: Optional[int]
    quote_folio: str
    customer_id: int
    branch_id: int
    items: List[QuoteItem] = field(default_factory=list)


@dataclass
class DeliveryAdjustment:
    order_id: int
    item_id: int
    original_quantity: float
    requested_quantity: float
    tolerance_units: float = 0.2
    status: str = "pending_customer"


@dataclass
class BranchNotification:
    branch_id: int
    title: str
    message: str
    severity: str
    dedupe_key: str
    sale_id: Optional[int] = None
    delivery_order_id: Optional[int] = None
    quote_id: Optional[int] = None
