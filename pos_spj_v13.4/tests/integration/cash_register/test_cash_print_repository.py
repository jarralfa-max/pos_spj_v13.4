import importlib
import sqlite3
import unittest

from backend.application.cash_register.printing import (
    CashPrintDocument,
    CashPrintDocumentType,
    CashPrintFormat,
    PrintCashDocumentCommand,
    PrintCashDocumentUseCase,
)
from backend.infrastructure.db.repositories.cash_register.unit_of_work import CashRegisterUnitOfWork
from backend.infrastructure.printing.cash_register_renderers import CashDocumentHtmlRenderer
from backend.shared.ids import new_uuid

cash_schema = importlib.import_module("migrations.standalone.175_cash_register_bounded_context_schema")


class Authorization:
    def __init__(self):
        self.calls = []

    def require(self, **values):
        self.calls.append(values)


def document():
    return CashPrintDocument(
        document_type=CashPrintDocumentType.Z_CUT,
        entity_id=new_uuid(),
        branch_id=new_uuid(),
        reference="CZ-2026-000001",
        title="Corte Z",
        fields=(("Cajero", "ana"),),
        totals=(("Diferencia", "$0.00"),),
        final=True,
    )


def command(doc, **changes):
    values = {
        "operation_id": new_uuid(),
        "actor_user_id": new_uuid(),
        "document": doc,
        "printer_id": "thermal-main",
        "output_format": CashPrintFormat.HTML,
    }
    values.update(changes)
    return PrintCashDocumentCommand(**values)


class CashPrintRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        cash_schema.run(self.conn)

    def tearDown(self):
        self.conn.close()

    def service(self, auth=None):
        self.uow = CashRegisterUnitOfWork(self.conn)
        return PrintCashDocumentUseCase(
            authorization=auth or Authorization(),
            renderers={CashPrintFormat.HTML: CashDocumentHtmlRenderer()},
            queue=self.uow.printing,
            audit=self.uow.printing,
        )

    def test_print_job_and_audit_are_persisted_and_idempotent(self):
        auth = Authorization()
        service = self.service(auth)
        doc = document()
        cmd = command(doc)

        print_id = service.execute(cmd)
        self.conn.commit()

        self.assertEqual(service.execute(cmd), print_id)
        self.assertEqual(auth.calls[0]["permission_code"], "CAJA.imprimir")
        job = self.conn.execute("SELECT id,status,document_type FROM cash_print_jobs").fetchone()
        audit = self.conn.execute("SELECT print_id,status,document_type FROM cash_print_audit").fetchone()
        self.assertEqual(job, (print_id, "QUEUED", "Z_CUT"))
        self.assertEqual(audit, (print_id, "QUEUED", "Z_CUT"))

    def test_reprint_validates_original_and_reason(self):
        auth = Authorization()
        service = self.service(auth)
        doc = document()
        original = service.execute(command(doc))
        self.conn.commit()

        reprint = service.execute(command(
            doc,
            original_print_id=original,
            reprint_reason="Papel danado",
        ))
        self.conn.commit()

        self.assertNotEqual(original, reprint)
        self.assertEqual(auth.calls[-1]["permission_code"], "CAJA.reimprimir")
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM cash_print_audit WHERE original_print_id=?",
                (original,),
            ).fetchone()[0],
            1,
        )


if __name__ == "__main__":
    unittest.main()
