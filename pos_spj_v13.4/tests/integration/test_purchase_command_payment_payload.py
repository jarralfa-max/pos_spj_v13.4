"""El payload de compra transporta una condición financiera coherente."""
from __future__ import annotations

from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]


# PUR-13: los tests que leían el fuente del monolito (_payment_method, _prov_repo)
# se retiraron — compras_pro.py fue eliminado. La derivación de la
# condición de pago vive en DirectPurchase/PurchaseService (validada abajo y en
# los tests del contexto de Compras).


def test_purchase_service_maps_condition_to_cxp_or_capital():
    """CREDITO → CxP; contado → asiento capital (nunca Caja)."""
    src = (APP_ROOT / "core" / "services" / "purchase_service.py").read_text(encoding="utf-8")
    assert "payment_method != 'CREDITO'" in src
    assert "crear_cxp" in src
    assert 'haber="capital_operativo"' in src
