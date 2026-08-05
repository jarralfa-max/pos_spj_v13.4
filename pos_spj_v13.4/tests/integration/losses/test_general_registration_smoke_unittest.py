import importlib
import sqlite3
import unittest
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.register_general_loss import GeneralLossLineInput, RegisterGeneralLossCommand, RegisterGeneralLossUseCase
from backend.domain.losses.enums import LossOrigin
from backend.infrastructure.persistence.losses_registration_repository import LossRegistrationRepository
from backend.shared.ids import new_uuid


class _Allow:
    def require(self, _user, _permission):
        return None


class GeneralRegistrationSmokeTest(unittest.TestCase):
    def test_transactional_outbox_and_idempotent_replay(self):
        db = sqlite3.connect(":memory:")
        importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(db)
        classification_id, reason_id = db.execute(
            "SELECT c.id,r.id FROM loss_classifications c JOIN loss_reasons r "
            "ON r.classification_id=c.id WHERE c.code='HANDLING_DAMAGE'").fetchone()
        actor, branch, warehouse, operation = new_uuid(), new_uuid(), new_uuid(), new_uuid()
        context = LossExecutionContext(actor, branch, frozenset({branch}), frozenset({warehouse}))
        command = RegisterGeneralLossCommand(
            operation_id=operation, context=context, warehouse_id=warehouse,
            classification_id=classification_id, reason_id=reason_id,
            origin=LossOrigin.INVENTORY,
            lines=(GeneralLossLineInput(new_uuid(), Decimal("1.250")),), submit=True)
        use_case = RegisterGeneralLossUseCase(LossRegistrationRepository(db), _Allow())

        first = use_case.execute(command)
        second = use_case.execute(command)

        self.assertFalse(first.replayed)
        self.assertTrue(second.replayed)
        self.assertEqual(1, db.execute("SELECT COUNT(*) FROM loss_cases").fetchone()[0])
        self.assertEqual(1, db.execute("SELECT COUNT(*) FROM loss_outbox").fetchone()[0])
        self.assertEqual("SUBMITTED", db.execute("SELECT status FROM loss_cases").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
