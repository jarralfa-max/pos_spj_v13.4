import unittest

from backend.application.cash_register.printing import (
    CashPrintDocument,
    CashPrintDocumentType,
    CashPrintFormat,
    CashQueuedPrintJob,
    DispatchCashPrintQueueUseCase,
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


class DispatchStore:
    def __init__(self, jobs):
        self.jobs = tuple(jobs)
        self.printed = []
        self.failed = []

    def list_pending_jobs(self, *, branch_id: str, limit: int = 25):
        return self.jobs[:limit]

    def mark_printed(self, *, print_id: str, actor_user_id: str, gateway_reference=None):
        self.printed.append((print_id, actor_user_id, gateway_reference))

    def mark_failed(self, *, print_id: str, actor_user_id: str, error: str):
        self.failed.append((print_id, actor_user_id, error))


class MixedGateway:
    def print_job(self, job):
        if job.filename.endswith("fail.html"):
            raise RuntimeError("printer offline")
        return f"gateway:{job.print_id}"


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
        self.assertEqual(authorization.calls[0]["permission_code"], "CAJA.imprimir")
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
        self.assertEqual(authorization.calls[-1]["permission_code"], "CAJA.reimprimir")

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

    def test_all_required_cash_24_documents_render_to_html_and_escpos(self):
        required = {
            CashPrintDocumentType.OPENING,
            CashPrintDocumentType.MOVEMENT_RECEIPT,
            CashPrintDocumentType.SAFE_DROP,
            CashPrintDocumentType.BLIND_COUNT,
            CashPrintDocumentType.X_CUT,
            CashPrintDocumentType.Z_CUT,
            CashPrintDocumentType.DIFFERENCE,
            CashPrintDocumentType.HANDOVER,
            CashPrintDocumentType.DEPOSIT_PREPARATION,
            CashPrintDocumentType.REFUND,
        }
        self.assertEqual({item for item in CashPrintDocumentType}, required)
        for document_type in required:
            with self.subTest(document_type=document_type.value):
                doc = sample_document(document_type)
                html = CashDocumentHtmlRenderer().render(doc)
                escpos = CashDocumentEscPosRenderer().render(doc)
                self.assertEqual(html.format, CashPrintFormat.HTML)
                self.assertEqual(escpos.format, CashPrintFormat.ESC_POS)
                self.assertIn(document_type.value.lower(), html.filename)

    def test_dispatch_queue_marks_printed_and_failed_without_stopping(self):
        actor = new_uuid()
        branch = new_uuid()
        ok = CashQueuedPrintJob(
            print_id=new_uuid(),
            printer_id="thermal-main",
            content=b"ok",
            media_type="text/html",
            filename="ok.html",
            copies=1,
        )
        fail = CashQueuedPrintJob(
            print_id=new_uuid(),
            printer_id="thermal-main",
            content=b"fail",
            media_type="text/html",
            filename="will-fail.html",
            copies=1,
        )
        store = DispatchStore([ok, fail])
        auth = Authorization()

        summary = DispatchCashPrintQueueUseCase(
            authorization=auth,
            store=store,
            gateway=MixedGateway(),
        ).execute(branch_id=branch, actor_user_id=actor)

        self.assertEqual((summary.processed, summary.printed, summary.failed), (2, 1, 1))
        self.assertEqual(store.printed[0][0], ok.print_id)
        self.assertEqual(store.failed[0][0], fail.print_id)
        self.assertIn("offline", store.failed[0][2])
        self.assertEqual(auth.calls[0]["permission_code"], "CAJA.imprimir")


if __name__ == "__main__":
    unittest.main()
