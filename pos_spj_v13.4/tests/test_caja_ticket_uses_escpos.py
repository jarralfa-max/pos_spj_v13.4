from backend.application.cash_register.printing import (
    CashPrintDocument,
    CashPrintDocumentType,
)
from backend.infrastructure.printing.cash_register_renderers import CashDocumentEscPosRenderer
from backend.shared.ids import new_uuid


def test_caja_corte_usa_renderer_escpos_canonico():
    document = CashPrintDocument(
        document_type=CashPrintDocumentType.Z_CUT,
        entity_id=new_uuid(),
        branch_id=new_uuid(),
        reference="CZ-2026-000009",
        title="Corte Z",
        fields=(("Fecha", "2026-01-01"), ("Cajero", "ana")),
        totals=(("Ventas", "$100.00"), ("Diferencia", "$0.00")),
        final=True,
    )
    artifact = CashDocumentEscPosRenderer().render(document)
    text = artifact.content.decode("cp850", errors="replace")
    assert artifact.media_type == "application/vnd.escpos"
    assert "CORTE Z" in text
    assert "CZ-2026-000009" in text
