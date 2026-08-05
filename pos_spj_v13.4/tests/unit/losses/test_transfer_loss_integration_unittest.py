import unittest
from contextlib import nullcontext
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.transfer_integration import (
    RegisterTransferClaimCommand, TransferLossIntegrationService,
)
from backend.domain.losses.exceptions import LossInvariantError
from backend.domain.losses.transfer_integration import ClaimPartyType, TransferLossPolicy
from backend.shared.ids import new_uuid


class Authorization:
    def __init__(self): self.calls = []
    def require(self, actor, permission): self.calls.append((actor, permission))


class Repository:
    def __init__(self, ids):
        self.ids, self.processed, self.saved, self.claims = ids, {}, [], []
        self.fact = {
            "transfer_id": ids["transfer"], "difference_id": ids["difference"],
            "resolution_id": ids["resolution"], "resolution_type": "CREATE_LOSS_CASE",
            "difference_type": "SHORT_QUANTITY", "responsible_stage": "TRANSIT",
            "expected_quantity": Decimal("10"), "actual_quantity": Decimal("7"),
            "expected_weight": Decimal("50"), "actual_weight": Decimal("35"),
            "product_id": ids["product"], "lot_id": ids["lot"],
            "branch_id": ids["branch"], "warehouse_id": ids["warehouse"],
            "receipt_id": ids["receipt"], "receipt_operation_id": ids["receipt_operation"],
            "inventory_receipt_posted": True,
        }
    def transaction(self): return nullcontext()
    def find_processed(self, op): return self.processed.get(op)
    def get_resolved_difference(self, **_): return self.fact
    def resolve_reason_id(self, _classification): return self.ids["reason"]
    def save_transfer_loss(self, **kw):
        self.saved.append(kw); case_id = kw["case"].id
        self.processed[kw["operation_id"]] = {"entity_id": case_id, "status": "SUBMITTED"}
    def get_transfer_loss(self, case_id):
        return ({"case_id": case_id, "branch_id": self.ids["branch"],
                 "warehouse_id": self.ids["warehouse"], "transfer_id": self.ids["transfer"]}
                if case_id == self.saved[0]["case"].id else None)
    def save_claim(self, **kw):
        self.claims.append(kw); claim_id = kw["claim_id"]
        self.processed[kw["operation_id"]] = {"entity_id": claim_id, "status": "OPEN"}
        return claim_id


def identifiers():
    return {name: new_uuid() for name in (
        "transfer", "difference", "resolution", "product", "lot", "branch", "warehouse",
        "receipt", "receipt_operation", "reason", "actor", "operation", "claim_operation",
        "responsible_party")}


class TransferLossIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.ids = identifiers(); self.repo = Repository(self.ids)
        self.service = TransferLossIntegrationService(self.repo, Authorization())
        self.context = LossExecutionContext(self.ids["actor"], self.ids["branch"],
            frozenset(), frozenset({self.ids["warehouse"]}))

    def test_resolved_shortage_creates_one_submitted_loss_without_second_inventory_post(self):
        payload = {"event_name": "LOSS_CASE_REQUESTED", "transfer_id": self.ids["transfer"],
            "difference_id": self.ids["difference"], "resolution_id": self.ids["resolution"],
            "operation_id": self.ids["operation"], "requested_by_user_id": self.ids["actor"]}
        first = self.service.request_loss_case(payload, context=self.context)
        replay = self.service.request_loss_case(payload, context=self.context)
        self.assertEqual(first.status, "SUBMITTED")
        self.assertTrue(replay.replayed)
        self.assertEqual(self.repo.saved[0]["case"].lines[0].quantity, Decimal("3"))
        self.assertEqual(self.repo.saved[0]["case"].lines[0].weight, Decimal("15"))
        self.assertEqual(self.repo.saved[0]["inventory_effect"], "POSTED_BY_TRANSFER_RECEIPT")

    def test_loss_case_requires_canonical_inventory_receipt_to_be_already_posted(self):
        self.repo.fact["inventory_receipt_posted"] = False
        with self.assertRaises(LossInvariantError):
            self.service.request_loss_case({"event_name": "LOSS_CASE_REQUESTED",
                "transfer_id": self.ids["transfer"], "difference_id": self.ids["difference"],
                "resolution_id": self.ids["resolution"], "operation_id": self.ids["operation"],
                "requested_by_user_id": self.ids["actor"]}, context=self.context)

    def test_claim_records_responsible_party_and_is_idempotent(self):
        payload = {"event_name": "LOSS_CASE_REQUESTED", "transfer_id": self.ids["transfer"],
            "difference_id": self.ids["difference"], "resolution_id": self.ids["resolution"],
            "operation_id": self.ids["operation"], "requested_by_user_id": self.ids["actor"]}
        case_id = self.service.request_loss_case(payload, context=self.context).case_id
        command = RegisterTransferClaimCommand(self.ids["claim_operation"], case_id,
            self.context, ClaimPartyType.CARRIER, self.ids["responsible_party"],
            Decimal("125.50"), "Daño durante traslado", ("evidence://claim/1",))
        first = self.service.register_claim(command); replay = self.service.register_claim(command)
        self.assertEqual(first.status, "OPEN")
        self.assertTrue(replay.replayed)
        self.assertEqual(self.repo.claims[0]["party_type"], "CARRIER")

    def test_overage_is_not_fabricated_as_a_loss(self):
        policy = TransferLossPolicy()
        with self.assertRaises(LossInvariantError):
            policy.assess(difference_type="OVER_QUANTITY", expected_quantity=Decimal("5"),
                          actual_quantity=Decimal("7"), expected_weight=Decimal("0"),
                          actual_weight=Decimal("0"), responsible_stage="RECEIVING")


if __name__ == "__main__": unittest.main()
