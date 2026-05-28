from pathlib import Path

SRC = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")


def test_mp_pending_reenables_cobrar_button():
    assert "finally:" in SRC
    assert "if not _worker_started:" in SRC
    assert "self._on_checkout_finished()" in SRC


def test_mp_pending_does_not_leave_checkout_running_true():
    assert "self._venta_checkout_running = False" in SRC


def test_mp_link_failure_does_not_clear_cart():
    start = SRC.find("if is_mercado_pago(datos_pago.get('forma_pago')):")
    end = SRC.find("# ── Guardrail: detectar ítems por debajo del costo", start)
    block = SRC[start:end]
    assert "raise RuntimeError(\"No se pudo generar link de pago MercadoPago.\")" in block
    fail_idx = block.find("raise RuntimeError(\"No se pudo generar link de pago MercadoPago.\")")
    clear_idx = block.find("self.cancelar_venta(silent=True)")
    assert clear_idx != -1 and clear_idx > fail_idx


def test_mp_pending_has_recoverable_context():
    assert '"compra": list(self.compra_actual)' in SRC
    assert '"totales": dict(self.totales)' in SRC
    assert '"datos_pago": dict(datos_pago or {})' in SRC
