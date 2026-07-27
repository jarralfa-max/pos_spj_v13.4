from __future__ import annotations
from enum import Enum
from typing import List
from pydantic import BaseModel, Field, field_validator


class AIIntentName(str, Enum):
    GREETING = "greeting"
    CREATE_ORDER = "create_order"
    ADD_PRODUCT = "add_product"
    REMOVE_PRODUCT = "remove_product"
    CONFIRM_ORDER = "confirm_order"
    CANCEL_ORDER = "cancel_order"
    CREATE_QUOTE = "create_quote"
    ACCEPT_QUOTE = "accept_quote"
    REJECT_QUOTE = "reject_quote"
    CONVERT_QUOTE_TO_ORDER = "convert_quote_to_order"
    SCHEDULE_ORDER = "schedule_order"
    CHANGE_BRANCH = "change_branch"
    SELECT_BRANCH = "select_branch"
    CHECK_ORDER_STATUS = "check_order_status"
    ACCEPT_ADJUSTMENT = "accept_adjustment"
    REJECT_ADJUSTMENT = "reject_adjustment"
    HUMAN_HANDOFF = "human_handoff"
    UNKNOWN = "unknown"


class AIWorkflowType(str, Enum):
    NONE = ""
    COUNTER = "counter"
    DELIVERY = "delivery"
    SCHEDULED = "scheduled"


class AIDeliveryType(str, Enum):
    NONE = ""
    PICKUP = "pickup"
    HOME_DELIVERY = "home_delivery"


class AIAdjustmentResponse(str, Enum):
    NONE = ""
    ACCEPT = "accept"
    REJECT = "reject"


class AIParsedProduct(BaseModel):
    product_name: str = ""
    quantity: float = 0
    unit: str = "kg"
    notes: str = ""


class AIIntentResult(BaseModel):
    intent: AIIntentName = AIIntentName.UNKNOWN
    confidence: float = 0.0
    workflow_type: AIWorkflowType = AIWorkflowType.NONE
    delivery_type: AIDeliveryType = AIDeliveryType.NONE
    branch_reference: str = ""
    scheduled_at: str = ""
    products: List[AIParsedProduct] = Field(default_factory=list)
    quote_reference: str = ""
    order_reference: str = ""
    adjustment_response: AIAdjustmentResponse = AIAdjustmentResponse.NONE
    needs_clarification: bool = False
    clarification_question: str = ""

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v or 0.0)))

