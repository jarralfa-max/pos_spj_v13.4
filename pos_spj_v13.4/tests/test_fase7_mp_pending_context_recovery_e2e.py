from pathlib import Path

SRC = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")


def test_mp_pending_context_keeps_required_fields_for_recovery():
    required = [
        '"estado": "pendiente_pago"',
        '"folio": folio_pend',
        '"url_pago": link',
        '"cliente_id": cliente_id',
        '"cliente": dict(self.cliente_actual or {})',
        '"compra": list(self.compra_actual)',
        '"totales": dict(self.totales)',
        '"datos_pago": dict(datos_pago or {})',
    ]
    for needle in required:
        assert needle in SRC


def test_mp_pending_cleanup_path_unblocks_ui_even_on_early_return():
    assert "finally:" in SRC
    assert "if not _worker_started:" in SRC
    assert "self._on_checkout_finished()" in SRC
