from pathlib import Path

SRC = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")


def test_no_ticket_from_compra_actual_postventa():
    assert "_items_snapshot = list(self.compra_actual)" not in SRC
    assert "def generar_ticket(" not in SRC


def test_no_venta_id_equals_folio_in_ticket_payload():
    assert "'venta_id': folio" not in SRC
    assert "'folio':    venta[0], 'venta_id': int(vid)" in SRC


def test_no_ui_final_points_calculation():
    assert "puntos_resultado =" not in SRC
    assert "loyalty_result = dict(getattr(result, \"loyalty_result\"" in SRC


def test_no_false_print_fallback():
    assert "def _procesar_venta_via_uc(" not in SRC
