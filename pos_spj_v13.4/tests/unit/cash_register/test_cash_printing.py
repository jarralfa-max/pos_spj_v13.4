import unittest

from backend.application.cash_register.printing import (
    CashPrintDocument,
    CashPrintDocumentType,
    CashPrintFormat,
    InMemoryCashPrintAuditRepository,
    InMemoryCashPrintQueue,
    PrintCashDocumentCommand,
    PrintCashDocumentUseCase,
)
from backend.infrastructure.printing.cash_register_renderers import (
    CUT_PARTIAL,
    INIT,
    CashDocumentEscPosRenderer,
    CashDocumentHtmlRenderer,
)
from backend.shared.ids import new_uuid


class Authorization:
    def __init__(self):
        self.calls = []

    def require(self, **values):
        self.calls.append(values)


class FailingQueue(InMemoryCashPrintQueue):
    def enqueue(self, job):
        raise RuntimeError("printer queue offline")


def sample_document(document_type=CashPrintDocumentType.Z_CUT):
    return CashPrintDocument(
        document_type=document_type,
        entity_id=new_uuid(),
        branch_id=new_uuid(),
        reference="CZ-2026-000001",
        title="Corte Z",
        fields=(("Sucursal", "Matriz & Norte"), ("Cajero", "admin")),
        lines=(("Efectivo esperado", "$100.00"), ("Efectivo contado", "$98.50")),
        totals=(("Diferencia", "-$1.50"),),
        barcode_value="CZ-2026-000001",
        qr_value="cash:z:1",
        final=True,
    )


def command(document=None, **changes):
    values = {
        "operation_id": new_uuid(),
        "actor_user_id": new_uuid(),
        "document": document or sample_document(),
        "printer_id": "thermal-main",
        "output_format": CashPrintFormat.HTML,
        "copies": 1,
    }
    values.update(changes)
    return PrintCashDocumentCommand(**values)


class CashPrintingTests(unittest.TestCase):
    def make_use_case(self, queue=None, audit=None, authorization=None):
        return PrintCashDocumentUseCase(
            authorization=authorization or Authorization(),
            renderers={
                CashPrintFormat.HTML: CashDocumentHtmlRenderer(),
                CashPrintFormat.ESC_POS: CashDocumentEscPosRenderer(),
            },
            queue=queue or InMemoryCashPrintQueue(),
            audit=audit or InMemoryCashPrintAuditRepository(),
        )

    def test_print_is_rendered_queued_audited_and_idempotent(self):
        authorization = Authorization()
        queue = InMemoryCashPrintQueue()
        audit = InMemoryCashPrintAuditRepository()
        service = self.make_use_case(queue=queue, audit=audit, authorization=authorization)
        cmd = command()

        print_id = service.execute(cmd)

        self.assertEqual(service.execute(cmd), print_id)
        self.assertEqual(len(queue.jobs), 1)
        self.assertEqual(queue.jobs[0].print_id, print_id)
        self.assertEqual(audit.records[0]["status"], "QUEUED")
        self.assertEqual(
            audit.records[0]["event_payload"]["payload"]["document_type"],
            CashPrintDocumentType.Z_CUT.value,
        )
        self.assertEqual(authorization.calls[0]["permission_code"], "CASH_PRINT")
        self.assertIn(b"Matriz &amp; Norte", queue.jobs[0].artifact.content)

    def test_reprint_requires_reason_and_original_document(self):
        document = sample_document(CashPrintDocumentType.X_CUT)
        with self.assertRaisesRegex(ValueError, "reason"):
            command(document=document, original_print_id=new_uuid())

        authorization = Authorization()
        queue = InMemoryCashPrintQueue()
        audit = InMemoryCashPrintAuditRepository()
        service = self.make_use_case(queue=queue, audit=audit, authorization=authorization)
        original = service.execute(command(document=document))

        reprint = service.execute(command(
            document=document,
            original_print_id=original,
            reprint_reason="Ticket danado por impresora",
        ))

        self.assertNotEqual(original, reprint)
        self.assertEqual(len(queue.jobs), 2)
        self.assertEqual(queue.jobs[-1].original_print_id, original)
        self.assertEqual(authorization.calls[-1]["permission_code"], "CASH_REPRINT")

    def test_reprint_rejects_original_from_another_document(self):
        audit = InMemoryCashPrintAuditRepository()
        queue = InMemoryCashPrintQueue()
        service = self.make_use_case(queue=queue, audit=audit)
        original = service.execute(command(document=sample_document(CashPrintDocumentType.Z_CUT)))

        with self.assertRaisesRegex(ValueError, "Original"):
            service.execute(command(
                document=sample_document(CashPrintDocumentType.Z_CUT),
                original_print_id=original,
                reprint_reason="Documento equivocado",
            ))

    def test_queue_failures_are_audited(self):
        service = self.make_use_case(queue=FailingQueue(), audit=InMemoryCashPrintAuditRepository())
        with self.assertRaisesRegex(RuntimeError, "offline"):
            service.execute(command())

    def test_escpos_renderer_is_sanitized_and_cut(self):
        renderer = CashDocumentEscPosRenderer()
        artifact = renderer.render(sample_document())
        self.assertTrue(artifact.content.startswith(INIT))
        self.assertTrue(artifact.content.endswith(CUT_PARTIAL))
        text = artifact.content.decode("cp850", errors="replace")
        self.assertNotIn("ñ", text)
        self.assertIn("Corte Z".upper(), text)
        preview = renderer.render_text_preview(sample_document())
        self.assertLessEqual(max(len(line) for line in preview.splitlines()), 32)


if __name__ == "__main__":
    unittest.main()
