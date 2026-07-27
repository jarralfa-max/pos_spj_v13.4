from pathlib import Path

SRC = Path('pos_spj_v13.4/modulos/ventas.py').read_text(encoding='utf-8')


def test_ui_uses_result_ticket_payload_not_compra_actual():
    assert "def _aplicar_resultado_venta" in SRC
    assert "dict(getattr(result, \"ticket_payload\"" in SRC
    assert "_items_snapshot = list(self.compra_actual)" not in SRC


def test_ui_uses_result_total_not_self_totales():
    assert "Total: ${float(getattr(result, 'total'" in SRC
    assert "Total: ${self.totales['total_final']" not in SRC


def test_ui_uses_result_venta_id_not_folio():
    assert '"venta_id": getattr(result, "venta_id"' in SRC
    assert "'venta_id': folio" not in SRC


def test_ui_updates_points_from_result_loyalty():
    assert "loyalty_result = dict(getattr(result, \"loyalty_result\"" in SRC
    assert 'self.cliente_actual["puntos"] = puntos_totales' in SRC


def test_ui_queries_real_saldo_if_loyalty_result_missing():
    assert "ls.saldo(cliente_id)" in SRC


def test_ui_does_not_clear_cart_if_uc_failed():
    block_start = SRC.find("def _on_checkout_success")
    block_end = SRC.find("def _on_checkout_failed")
    block = SRC[block_start:block_end]
    assert "if not getattr(_r, \"ok\", False):" in block
    assert "return" in block


def test_ui_clears_cart_if_sale_ok_even_print_failed():
    assert "self._imprimir_ticket_consolidado(datos_ticket)" in SRC
    assert "self.cancelar_venta(silent=True)" in SRC
