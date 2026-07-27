from pathlib import Path


def test_phase11_payment_dialog_extracted_and_used():
    p = Path('pos_spj_v13.4/presentation/sales/dialogs/payment_dialog.py')
    assert p.exists()
    src_ui = Path('pos_spj_v13.4/modulos/ventas.py').read_text(encoding='utf-8')
    assert 'from presentation.sales.dialogs.payment_dialog import DialogoPago as PaymentDialog' in src_ui
    assert 'dialogo = PaymentDialog(' in src_ui
