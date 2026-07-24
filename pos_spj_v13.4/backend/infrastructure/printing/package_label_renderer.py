"""Portable package-label renderer; device conversion belongs to the print gateway."""
from backend.application.transfers.printing import (
    TransferPrintArtifact, TransferPrintDocument,
)
from .transfer_document_renderer import _filename_token


class PackageLabelRenderer:
    def render(self, document: TransferPrintDocument) -> TransferPrintArtifact:
        clean = lambda value: str(value).replace("\r", " ").replace("\n", " ")
        payload = [clean(document.title), clean(document.reference)]
        payload.extend(f"{clean(label)}: {clean(value)}" for label, value in document.fields)
        if document.barcode_value:
            payload.append(f"BARCODE:{clean(document.barcode_value)}")
        if document.qr_value:
            payload.append(f"QR:{clean(document.qr_value)}")
        return TransferPrintArtifact(
            "\n".join(payload).encode("utf-8"), "text/plain",
            f"package-{_filename_token(document.reference)}.txt")
