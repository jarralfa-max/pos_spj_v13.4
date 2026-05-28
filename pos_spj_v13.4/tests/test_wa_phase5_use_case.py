import os
import sys
from unittest.mock import MagicMock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ROOT)
WA_SVC_PATH = os.path.join(_REPO, "whatsapp_service")
for _p in (WA_SVC_PATH, _ROOT):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def test_confirm_order_use_case_uses_policy_not_hardcoded_50():
    import importlib.util
    uc_path = os.path.join(WA_SVC_PATH, "application", "confirm_order_use_case.py")
    spec = importlib.util.spec_from_file_location("wa_confirm_order_uc", uc_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wa_confirm_order_uc"] = mod
    spec.loader.exec_module(mod)
    ConfirmWhatsAppOrderCommand = mod.ConfirmWhatsAppOrderCommand
    ConfirmWhatsAppOrderUseCase = mod.ConfirmWhatsAppOrderUseCase
    erp = MagicMock()
    erp.crear_pedido_wa.return_value = {"venta_id": 1, "folio": "WA-1", "total": 200.0}
    erp.requiere_anticipo.return_value = True
    erp.calcular_anticipo_rules.return_value = {"requiere": True, "monto": 30.0, "razon": "policy"}

    uc = ConfirmWhatsAppOrderUseCase(erp=erp, orchestrator=None)
    out = uc.execute(ConfirmWhatsAppOrderCommand(
        phone="+521",
        cliente_id=10,
        sucursal_id=1,
        tipo_entrega="sucursal",
        direccion="",
        items=[{"producto_id": 1, "nombre": "P", "cantidad": 2.0, "precio_unitario": 100.0}],
        pedido_programado=False,
    ))
    assert out.anticipo_requerido is True
    assert out.anticipo_monto == 30.0
