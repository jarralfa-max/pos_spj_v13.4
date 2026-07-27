"""El payload de compra transporta una condición financiera coherente."""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


def test_direct_and_pr_flows_share_payment_derivation():
    src = (APP_ROOT / "modulos" / "compras_pro.py").read_text(encoding="utf-8")
    # Ambos flujos (DIRECT y PR) derivan el método con la misma función
    assert src.count("pago        = self._payment_method()") + \
           src.count("pago     = self._payment_method()") == 2


def test_purchase_service_maps_condition_to_cxp_or_capital():
    """CREDITO → CxP; contado → asiento capital (nunca Caja)."""
    src = (APP_ROOT / "core" / "services" / "purchase_service.py").read_text(encoding="utf-8")
    assert "payment_method != 'CREDITO'" in src
    assert "crear_cxp" in src
    assert 'haber="capital_operativo"' in src


def test_prov_repo_is_plain_attribute_not_property():
    """Regresión: property '_prov_repo' has no setter (chocaba con hotfixes).

    El repositorio se asigna como atributo plano en __init__ y admite
    reasignación (self._prov_repo = ...).
    """
    src = (APP_ROOT / "modulos" / "compras_pro.py").read_text(encoding="utf-8")
    assert "self._prov_repo = ProveedorRepository(container.db)" in src
    # No debe existir property _prov_repo (impediría asignaciones)
    import re
    assert not re.search(r"@property\s+def _prov_repo\(", src)
