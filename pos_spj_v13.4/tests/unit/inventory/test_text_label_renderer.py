"""SET-14 cutover — render_text_label: plain-text fallback/preview."""

from __future__ import annotations

from backend.domain.inventory.enums import LabelType
from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.infrastructure.hardware.label_rendering.text_label_renderer import render_text_label


def _doc(**overrides) -> LabelDocument:
    kwargs = dict(label_type=LabelType.LOT, title="Bistec", lines=("Lote: L-01",))
    kwargs.update(overrides)
    return LabelDocument(**kwargs)


class TestRenderTextLabel:
    def test_exact_output_for_title_and_lines(self):
        data = render_text_label(_doc(title="Bistec", lines=("Lote: L-01", "Caduca: 2026-09-01")), copies=1)
        assert data.decode("utf-8") == "Bistec\nLote: L-01\nCaduca: 2026-09-01"

    def test_barcode_and_qr_are_rendered_as_readable_lines(self):
        data = render_text_label(_doc(barcode="L-01", qr_payload="lot:L-01"), copies=1).decode("utf-8")
        assert "[Código: L-01]" in data
        assert "[QR: lot:L-01]" in data

    def test_copies_joined_by_form_feed(self):
        data = render_text_label(_doc(), copies=2).decode("utf-8")
        assert data.count("\f") == 1
        block, _, rest = data.partition("\f")
        assert block == rest

    def test_copies_below_one_clamped_to_one(self):
        data = render_text_label(_doc(), copies=0).decode("utf-8")
        assert "\f" not in data
