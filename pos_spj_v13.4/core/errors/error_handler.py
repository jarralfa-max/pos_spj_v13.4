
# core/errors/error_handler.py — SPJ POS v6.1
from __future__ import annotations
import logging, traceback

logger = logging.getLogger("spj.error_handler")

class SPJError(Exception):
    def __init__(self, mensaje, codigo="SPJ_ERROR", detalles=None, safe_message=None):
        super().__init__(mensaje)
        self.codigo = codigo; self.detalles = detalles
        self.safe_message = safe_message or mensaje

class StockInsuficienteError(SPJError):
    def __init__(self, producto, disponible, requerido):
        super().__init__(
            f"Stock insuficiente: {producto}",
            codigo="STOCK_INSUFICIENTE",
            safe_message=f"Sin stock suficiente de '{producto}'\nDisponible: {disponible:.2f} | Requerido: {requerido:.2f}"
        )
        self.producto = producto; self.disponible = disponible; self.requerido = requerido

class VentaError(SPJError): pass
class InventarioError(SPJError): pass

def handle(exc, context="", show_ui=True, usuario="Sistema") -> str:
    tb_str = traceback.format_exc()
    safe_msg = getattr(exc, "safe_message", str(exc))
    logger.error("[%s] %s — %s", type(exc).__name__, exc, context)
    try:
        from core.services.audit_service import log as audit_log
        audit_log("ERROR", context or "desconocido", usuario=usuario,
                  detalles=f"{type(exc).__name__}: {exc}\n{tb_str[:500]}")
    except Exception:
        pass
    if show_ui:
        try:
            from PyQt5.QtWidgets import QApplication, QMessageBox
            if QApplication.instance():
                mb = QMessageBox()
                mb.setWindowTitle("Error"); mb.setIcon(QMessageBox.Warning)
                mb.setText(safe_msg); mb.exec_()
        except Exception:
            pass
    return safe_msg
