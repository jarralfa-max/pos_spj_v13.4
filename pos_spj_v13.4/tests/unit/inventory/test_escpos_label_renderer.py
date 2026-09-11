"""SET-14 cutover — render_escpos_label: reuses
las constantes de `backend/infrastructure/printing/escpos.py` y
Code-128/QR raster rendering. Structural assertions (command bytes
present/absent, title/lines encoded, copies repeated) — the raster
byte-generation itself is already covered by the ticket renderer's own
tests.
"""

from __future__ import annotations

from backend.infrastructure.printing.escpos import CUT_PARTIAL, INIT
from backend.domain.inventory.enums import LabelType
from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.infrastructure.hardware.label_rendering.escpos_label_renderer import render_escpos_label


def _doc(**overrides) -> LabelDocument:
    kwargs = dict(label_type=LabelType.LOT, title="Bistec", lines=("Lote: L-01",))
    kwargs.update(overrides)
    return LabelDocument(**kwargs)


class TestRenderEscposLabel:
    def test_starts_with_init_and_contains_title(self):
        data = render_escpos_label(_doc(), copies=1)
        assert data.startswith(INIT)
        assert b"Bistec" in data

    def test_contains_body_lines(self):
        data = render_escpos_label(_doc(lines=("Lote: L-01", "Caduca: 2026-09-01")), copies=1)
        assert b"Lote: L-01" in data
        assert b"Caduca: 2026-09-01" in data

    def test_ends_with_cut(self):
        data = render_escpos_label(_doc(), copies=1)
        assert data.endswith(CUT_PARTIAL)

    def test_no_barcode_or_qr_yields_shorter_output_than_with_them(self):
        bare = render_escpos_label(_doc(), copies=1)
        with_codes = render_escpos_label(_doc(barcode="L-01", qr_payload="lot:L-01"), copies=1)
        assert len(with_codes) > len(bare)  # real raster bytes were appended

    def test_copies_repeats_the_whole_rendered_block(self):
        one = render_escpos_label(_doc(), copies=1)
        two = render_escpos_label(_doc(), copies=2)
        assert two == one + one

    def test_copies_below_one_clamped_to_one(self):
        zero = render_escpos_label(_doc(), copies=0)
        one = render_escpos_label(_doc(), copies=1)
        assert zero == one
