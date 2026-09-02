"""SET-14 cutover — render_zpl: real Zebra ZPL II generation for a
LabelDocument. Protocol-correctness verified via exact-string assertions
(no physical printer available in this environment to validate against —
same discipline `core/ticket_escpos_renderer.py` already operates under).
"""

from __future__ import annotations

from backend.domain.inventory.enums import LabelType
from backend.domain.inventory.value_objects.label_document import LabelDocument
from backend.infrastructure.hardware.label_rendering.zpl_renderer import render_zpl


def _doc(**overrides) -> LabelDocument:
    kwargs = dict(label_type=LabelType.LOT, title="Bistec", lines=("Lote: L-01",))
    kwargs.update(overrides)
    return LabelDocument(**kwargs)


class TestRenderZpl:
    def test_starts_and_ends_with_format_markers(self):
        data = render_zpl(_doc(), copies=1)
        assert data.startswith(b"^XA")
        assert data.endswith(b"^XZ")

    def test_title_and_lines_are_rendered_as_text_fields(self):
        data = render_zpl(_doc(title="Bistec", lines=("Lote: L-01", "Caduca: 2026-09-01")), copies=1)
        assert b"^FDBistec^FS" in data
        assert b"^FDLote: L-01^FS" in data
        assert b"^FDCaduca: 2026-09-01^FS" in data

    def test_exact_output_for_title_only_no_barcode_no_qr(self):
        data = render_zpl(_doc(title="Bistec", lines=()), copies=1)
        assert data == b"^XA^FO20,20^A0N,30,30^FDBistec^FS^PQ1^XZ"

    def test_barcode_present_adds_bc_command(self):
        data = render_zpl(_doc(barcode="L-01"), copies=1)
        assert b"^BY2" in data
        assert b"^BCN,60,Y,N,N" in data
        assert b"^FDL-01^FS" in data

    def test_no_barcode_omits_bc_command(self):
        data = render_zpl(_doc(), copies=1)
        assert b"^BC" not in data

    def test_qr_present_adds_bq_command_with_model_2(self):
        data = render_zpl(_doc(qr_payload="lot:L-01"), copies=1)
        assert b"^BQN,2,4" in data
        assert b"^FDLA,lot:L-01^FS" in data

    def test_no_qr_omits_bq_command(self):
        data = render_zpl(_doc(), copies=1)
        assert b"^BQ" not in data

    def test_copies_sets_print_quantity(self):
        data = render_zpl(_doc(), copies=5)
        assert b"^PQ5^XZ" in data

    def test_copies_below_one_clamped_to_one(self):
        data = render_zpl(_doc(), copies=0)
        assert b"^PQ1^XZ" in data

    def test_caret_and_tilde_in_text_are_stripped_not_left_to_break_the_field(self):
        data = render_zpl(_doc(title="Precio^Especial~Hoy"), copies=1)
        assert b"^FDPrecioEspecialHoy^FS" in data

    def test_newline_in_line_is_flattened_to_a_single_space(self):
        data = render_zpl(_doc(lines=("linea\ncon\nsaltos",)), copies=1)
        assert b"^FDlinea con saltos^FS" in data
