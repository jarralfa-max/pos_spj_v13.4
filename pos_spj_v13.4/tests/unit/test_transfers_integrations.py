from decimal import Decimal

import pytest

from backend.application.transfers.integrations.inventory_gateway import CanonicalInventoryTransferGateway
from backend.application.transfers.integrations.outbound_handlers import (
    TransferEconomicImpactHandler,
    TransferLossCaseRequestedHandler,
)
from backend.application.transfers.integrations.product_profiles import (
    CanonicalProductTransferProfileQueryService,
    ProductQualityTransferRules,
)
from backend.application.transfers.integrations.requirement_handlers import (
    PosStockReplenishmentHandler,
    ProductionMaterialTransferHandler,
    SalesCustomerOrderTransferHandler,
)
from backend.application.transfers.queries.order_transfer_status_query import (
    OrderTransferStatusDTO,
)
from backend.domain.transfers.enums import TransferNodeType, TransferType
from backend.domain.transfers.events import TransferEvents
from backend.domain.transfers.value_objects.transfer_node import TransferNode


class ExecutePort:
    def __init__(self): self.calls = []
    def execute(self, request): self.calls.append(request)


class ReturnPort:
    def __init__(self): self.dispatches, self.receipts = [], []
    def dispatch(self, request): self.dispatches.append(request)
    def receive(self, request): self.receipts.append(request)


def test_inventory_gateway_has_one_explicit_use_case_per_ledger_operation():
    reserve, allocate, dispatch, receipt, returns = (
        ExecutePort(), ExecutePort(), ExecutePort(), ExecutePort(), ReturnPort())
    gateway = CanonicalInventoryTransferGateway(reserve, allocate, dispatch, receipt, returns)
    allocation = object()
    gateway.reserve(transfer="transfer", operation_id="reserve", actor_id="user",
                    allocations=(allocation,))
    gateway.dispatch(transfer="transfer", operation_id="dispatch", actor_id="user")
    gateway.receive(transfer="transfer", receipt="receipt", operation_id="receive", actor_id="user")
    gateway.dispatch_return(transfer_return="return", operation_id="return-out", actor_id="user")
    gateway.receive_return(transfer_return="return", operation_id="return-in", actor_id="user")

    assert reserve.calls[0].operation_id == "reserve"
    assert allocate.calls[0].allocations == (allocation,)
    assert dispatch.calls[0].operation_id == "dispatch"
    assert receipt.calls[0].receipt == "receipt"
    assert returns.dispatches[0].operation_id == "return-out"
    assert returns.receipts[0].operation_id == "return-in"


class Units:
    def is_unit_supported(self, **values): return values["unit_id"] == "kg"


class CatchWeight:
    def is_catch_weight(self, product_id): return True


class Quality:
    def get_transfer_rules(self, product_id):
        return ProductQualityTransferRules(
            lot_required=False, quality_required=True, temperature_required=True,
            minimum_temperature=Decimal("0"), maximum_temperature=Decimal("4"),
            temperature_warning_margin=Decimal("0.5"))


class ShelfLife:
    def requires_expiration_tracking(self, product_id): return True


def test_product_profile_composes_unit_catch_weight_shelf_life_and_quality_owners():
    service = CanonicalProductTransferProfileQueryService(
        Units(), CatchWeight(), Quality(), ShelfLife())
    service.validate_unit(product_id="meat", unit_id="kg")
    profile = service.get_transfer_profile("meat")
    assert profile.catch_weight is True
    assert profile.lot_required is True
    assert profile.quality_required is True
    assert profile.maximum_temperature == Decimal("4")
    with pytest.raises(ValueError, match="unit"):
        service.validate_unit(product_id="meat", unit_id="free-text-unit")


class CreateRequest:
    def __init__(self): self.commands = []
    def execute(self, command): self.commands.append(command); return command


class Nodes:
    def get_node(self, node_id):
        return TransferNode(TransferNodeType.WAREHOUSE, node_id, f"{node_id}-warehouse")


@pytest.mark.parametrize(("handler_type", "event_name", "transfer_type", "channel"), (
    (SalesCustomerOrderTransferHandler, "CUSTOMER_ORDER_REQUIRES_TRANSFER",
     TransferType.CUSTOMER_ORDER_TRANSFER, "SALES"),
    (PosStockReplenishmentHandler, "STOCK_REPLENISHMENT_REQUIRED",
     TransferType.REPLENISHMENT_TRANSFER, "POS"),
    (ProductionMaterialTransferHandler, "PRODUCTION_MATERIAL_TRANSFER_REQUIRED",
     TransferType.PRODUCTION_SUPPLY_TRANSFER, "PRODUCTION"),
))
def test_sales_pos_and_production_only_create_transfer_needs(
        handler_type, event_name, transfer_type, channel):
    create = CreateRequest()
    result = handler_type(create, Nodes()).handle({
        "event_name": event_name, "user_id": "integration-user",
        "operation_id": f"{channel}-operation", "entity_id": f"{channel}-document",
        "origin_node_id": "origin", "destination_node_id": "destination",
        "lines": [{"product_id": "product", "unit_id": "unit",
                   "quantity": "4", "weight": "100"}],
    })
    assert result.transfer_type is transfer_type
    assert result.source_channel == channel
    assert result.source_reference_id == f"{channel}-document"
    assert result.lines[0].requested_weight == Decimal("100")


def test_inbound_requirements_reject_ambiguous_flags_and_float_values():
    handler = PosStockReplenishmentHandler(CreateRequest(), Nodes())
    base_event = {
        "event_name": "STOCK_REPLENISHMENT_REQUIRED", "user_id": "user",
        "operation_id": "operation", "entity_id": "document",
        "origin_node_id": "origin", "destination_node_id": "destination",
        "lines": [{"product_id": "product", "unit_id": "kg", "quantity": "1"}],
    }
    with pytest.raises(TypeError, match="booleans"):
        handler.handle({**base_event, "cold_chain_required": "false"})
    with pytest.raises(TypeError, match="decimal strings"):
        handler.handle({**base_event, "lines": [{"product_id": "product",
                                                  "unit_id": "kg", "quantity": 1.0}]})


def test_sales_pos_status_contract_requires_decimal_available_to_promise():
    status = OrderTransferStatusDTO("order", "transfer", "IN_TRANSIT", None,
                                    Decimal("12.500"))
    assert status.available_to_promise == Decimal("12.500")
    with pytest.raises(TypeError, match="Decimal"):
        OrderTransferStatusDTO("order", "transfer", "IN_TRANSIT", None, 12.5)


class LossGateway:
    def __init__(self): self.items = []
    def request_loss_case(self, payload): self.items.append(payload)


class EconomicGateway:
    def __init__(self): self.items = []
    def record_transfer_impact(self, event_name, payload): self.items.append((event_name, payload))


def test_loss_and_cost_handlers_forward_only_canonical_fact_events():
    loss = LossGateway()
    TransferLossCaseRequestedHandler(loss).handle({
        "event_name": TransferEvents.DIFFERENCE_RESOLVED,
        "resolution_type": "CREATE_LOSS_CASE", "entity_id": "transfer",
        "difference_id": "difference", "resolution_id": "resolution",
        "operation_id": "operation", "user_id": "resolver",
    })
    assert loss.items[0]["event_name"] == "LOSS_CASE_REQUESTED"
    assert loss.items[0]["difference_id"] == "difference"

    economic = EconomicGateway()
    handler = TransferEconomicImpactHandler(economic)
    for event_name in handler.SUPPORTED_EVENTS:
        handler.handle({"event_name": event_name, "entity_id": "transfer"})
    assert {item[0] for item in economic.items} == handler.SUPPORTED_EVENTS
    with pytest.raises(ValueError):
        handler.handle({"event_name": "ACCOUNT_SELECTED"})
