import pytest

from backend.application.transfers.printing import (
    PrintTransferDocumentCommand, PrintTransferDocumentUseCase,
    TransferDocumentType, TransferPrintDocument,
)
from backend.infrastructure.printing.package_label_renderer import PackageLabelRenderer
from backend.infrastructure.printing.transfer_document_renderer import (
    TransferDocumentHtmlRenderer,
)


class Authorization:
    def __init__(self): self.calls = []
    def require(self, **values): self.calls.append(values)


class Gateway:
    def __init__(self, fail=False): self.calls, self.fail = [], fail
    def print(self, **values):
        self.calls.append(values)
        if self.fail:
            raise RuntimeError("printer offline")


class Audit:
    def __init__(self): self.by_operation, self.records, self.originals = {}, [], set()
    def print_id_for_operation(self, operation_id): return self.by_operation.get(operation_id)
    def original_exists(self, print_id, transfer_id): return (print_id, transfer_id) in self.originals
    def record(self, **values):
        self.records.append(values)
        self.by_operation[values["command"].operation_id] = values["print_id"]


def document(document_type=TransferDocumentType.TRANSFER):
    return TransferPrintDocument(document_type, "transfer-1", "TRF-2026-000001",
                                 "Transferencia", (("Origen", "Matriz & Norte"),),
                                 (("Producto", "1.250 kg"),), "PKG-1", "TRF:1")


def use_case(gateway=None, audit=None):
    gateway, audit = gateway or Gateway(), audit or Audit()
    authorization = Authorization()
    html = TransferDocumentHtmlRenderer()
    use_case = PrintTransferDocumentUseCase(
        authorization=authorization,
        renderers={TransferDocumentType.TRANSFER: html,
                   TransferDocumentType.PICKING_LIST: html,
                   TransferDocumentType.SHIPMENT: html,
                   TransferDocumentType.RECEIPT: html,
                   TransferDocumentType.PACKAGE_LABEL: PackageLabelRenderer()},
        gateway=gateway, audit=audit)
    return use_case, authorization, gateway, audit


def command(**changes):
    values = dict(operation_id="print-operation", actor_user_id="user-1",
                  document=document(), printer_id="printer-1", copies=1)
    values.update(changes)
    return PrintTransferDocumentCommand(**values)


def test_print_is_authorized_rendered_audited_and_idempotent():
    service, authorization, gateway, audit = use_case()
    print_id = service.execute(command())
    assert service.execute(command()) == print_id
    assert len(gateway.calls) == 1
    assert authorization.calls[0]["permission_code"] == "TRANSFERS_PRINT"
    assert audit.records[0]["status"] == "PRINTED"
    assert b"Matriz &amp; Norte" in gateway.calls[0]["artifact"].content


def test_reprint_requires_reason_and_existing_original_from_same_transfer():
    with pytest.raises(ValueError, match="reason"):
        command(original_print_id="original")
    service, authorization, _, audit = use_case()
    with pytest.raises(ValueError, match="Original"):
        service.execute(command(original_print_id="original", reprint_reason="Etiqueta dañada"))
    audit.originals.add(("original", "transfer-1"))
    result = service.execute(command(operation_id="reprint", original_print_id="original",
                                     reprint_reason="Etiqueta dañada"))
    assert result and audit.records[-1]["command"].reprint_reason == "Etiqueta dañada"
    assert authorization.calls[-1]["permission_code"] == "TRANSFERS_REPRINT"


def test_package_label_contains_barcode_and_qr_and_gateway_failures_are_audited():
    artifact = PackageLabelRenderer().render(document(TransferDocumentType.PACKAGE_LABEL))
    assert b"BARCODE:PKG-1" in artifact.content and b"QR:TRF:1" in artifact.content
    gateway, audit = Gateway(fail=True), Audit()
    service, _, _, _ = use_case(gateway, audit)
    with pytest.raises(RuntimeError, match="offline"):
        service.execute(command())
    assert audit.records[0]["status"] == "FAILED"


@pytest.mark.parametrize("copies", (0, 11))
def test_print_copy_limits_are_enforced(copies):
    with pytest.raises(ValueError, match="copies"):
        command(copies=copies)
