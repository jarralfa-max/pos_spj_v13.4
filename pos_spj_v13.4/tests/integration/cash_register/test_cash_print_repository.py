import importlib
import json
import sqlite3
import unittest

from backend.application.cash_register.printing import (
    CashPrintDocument,
    CashPrintDocumentType,
    CashPrintFormat,
    DispatchCashPrintQueueUseCase,
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


class RecordingGateway:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.jobs = []

    def print_job(self, job):
        self.jobs.append(job)
        if self.fail:
            raise RuntimeError("printer offline")
        return f"printed:{job.print_id}"


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
        row = self.conn.execute(
            """SELECT reprint_reason,event_payload_json
               FROM cash_print_audit WHERE original_print_id=?""",
            (original,),
        ).fetchone()
        self.assertEqual(row[0], "Papel danado")
        self.assertEqual(json.loads(row[1])["payload"]["reprint_reason"], "Papel danado")

    def test_dispatch_marks_printed_and_failed_in_queue_and_audit(self):
        auth = Authorization()
        service = self.service(auth)
        doc = document()
        print_id = service.execute(command(doc))
        self.conn.commit()

        gateway = RecordingGateway()
        summary = DispatchCashPrintQueueUseCase(
            authorization=auth,
            store=self.uow.printing,
            gateway=gateway,
        ).execute(branch_id=doc.branch_id, actor_user_id=new_uuid())
        self.conn.commit()

        self.assertEqual((summary.processed, summary.printed, summary.failed), (1, 1, 0))
        self.assertEqual(gateway.jobs[0].print_id, print_id)
        self.assertEqual(
            self.conn.execute("SELECT status FROM cash_print_jobs WHERE id=?", (print_id,)).fetchone()[0],
            "PRINTED",
        )
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM cash_print_audit WHERE print_id=? AND status='PRINTED'",
                (print_id,),
            ).fetchone()[0],
            1,
        )

        retry_doc = document()
        retry_id = service.execute(command(retry_doc))
        self.conn.commit()
        failed = DispatchCashPrintQueueUseCase(
            authorization=auth,
            store=self.uow.printing,
            gateway=RecordingGateway(fail=True),
        ).execute(branch_id=retry_doc.branch_id, actor_user_id=new_uuid())
        self.conn.commit()

        self.assertEqual((failed.processed, failed.printed, failed.failed), (1, 0, 1))
        self.assertEqual(
            self.conn.execute(
                "SELECT status,last_error FROM cash_print_jobs WHERE id=?",
                (retry_id,),
            ).fetchone(),
            ("FAILED", "printer offline"),
        )
        self.assertTrue(
            self.uow.printing.original_exists(
                retry_id,
                retry_doc.entity_id,
                retry_doc.document_type,
            )
        )


if __name__ == "__main__":
    unittest.main()
