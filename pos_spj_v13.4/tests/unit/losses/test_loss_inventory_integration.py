from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.loss_inventory_integration import (
    LossInventoryIntegrationService, PostLossInventoryCommand,
    RequestLossInventoryCommand, ReverseLossInventoryCommand,
)
from backend.domain.losses.enums import LossStatus
from backend.shared.ids import new_uuid


class _Auth:
    def require(self, _actor, _permission): pass


class _InventoryResult:
    success = True; message = "ok"; error_code = None; already_processed = False
    def __init__(self, entity_id): self.entity_id = entity_id


class _Inventory:
    def __init__(self): self.posted = None; self.reversed = None
    def post(self, movement, **_kwargs): self.posted = movement; return _InventoryResult(new_uuid())
    def reverse(self, **kwargs): self.reversed = kwargs; return _InventoryResult(new_uuid())


class _Tx:
    def __enter__(self): return self
    def __exit__(self, *_args): return False


class _Repository:
    def __init__(self):
        self.case_id = new_uuid(); self.movement_id = None; self.status = LossStatus.APPROVED
        self.events = []; self.operations = {}
    def transaction(self): return _Tx()
    def find_processed(self, operation_id): return self.operations.get(operation_id)
    def get_case_for_inventory(self, _case_id):
        return {"id": self.case_id, "branch_id": IDS[1], "warehouse_id": IDS[2],
                "status": self.status.value, "classification": "HANDLING_DAMAGE",
                "requires_inventory_posting": True, "inventory_movement_id": self.movement_id}
    def get_lines(self, _case_id):
        return [{"product_id": new_uuid(), "lot_id": None,
                 "quantity": Decimal("2.5"), "weight": Decimal("0"), "unit": "PZA"}]
    def get_available_location(self, _warehouse_id): return new_uuid()
    def has_posting_request(self, _case_id): return bool(self.events)
    def record_request(self, case_id, operation_id, event): self._record(case_id, operation_id, "APPROVED", event)
    def record_posted(self, case_id, operation_id, movement_id, event):
        self.movement_id = movement_id; self.status = LossStatus.INVENTORY_POSTED
        self._record(case_id, operation_id, self.status.value, event)
    def record_reversed(self, case_id, operation_id, _reversal_id, event):
        self.status = LossStatus.REVERSED; self._record(case_id, operation_id, self.status.value, event)
    def _record(self, case_id, operation_id, status, event):
        self.events.append(event); self.operations[operation_id] = (case_id, status)


IDS = new_uuid(), new_uuid(), new_uuid()
CTX = LossExecutionContext(IDS[0], IDS[1], frozenset({IDS[1]}), frozenset({IDS[2]}))


def test_request_post_and_reverse_use_inventory_gateway_without_direct_stock_write():
    repository, inventory = _Repository(), _Inventory()
    service = LossInventoryIntegrationService(repository, inventory, _Auth())
    service.request(RequestLossInventoryCommand(new_uuid(), repository.case_id, CTX))
    posted = service.post(PostLossInventoryCommand(new_uuid(), repository.case_id, CTX))
    reversed_result = service.reverse(ReverseLossInventoryCommand(
        new_uuid(), repository.case_id, CTX, "Corrección autorizada"))
    assert inventory.posted.source_module == "losses"
    assert inventory.posted.lines[0].quantity == Decimal("2.5")
    assert posted.status is LossStatus.INVENTORY_POSTED
    assert reversed_result.status is LossStatus.REVERSED


def test_replayed_request_is_idempotent():
    repository, inventory = _Repository(), _Inventory()
    service = LossInventoryIntegrationService(repository, inventory, _Auth())
    operation = new_uuid()
    service.request(RequestLossInventoryCommand(operation, repository.case_id, CTX))
    replay = service.request(RequestLossInventoryCommand(operation, repository.case_id, CTX))
    assert replay.replayed is True
    assert len(repository.events) == 1
