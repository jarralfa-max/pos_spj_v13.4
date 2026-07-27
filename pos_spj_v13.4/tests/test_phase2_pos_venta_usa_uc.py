from pathlib import Path


def test_pos_venta_usa_uc():
    src = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")
    start = src.find("def _procesar_venta_via_uc")
    assert start >= 0
    end = src.find("\n    def ", start + 1)
    block = src[start:end if end > start else None]

    assert "_uc.ejecutar(" in block
    assert "execute_sale(" not in block


def test_pos_venta_falla_si_uc_no_disponible():
    src = Path("pos_spj_v13.4/modulos/ventas.py").read_text(encoding="utf-8")
    assert "ProcesarVentaUC no disponible" in src
