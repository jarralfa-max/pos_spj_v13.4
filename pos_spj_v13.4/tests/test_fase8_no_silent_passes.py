from concurrent.futures import ThreadPoolExecutor
import threading
from pathlib import Path

import pytest

from core.events.domain_events import SALE_ITEMS_PROCESS
from core.events.event_bus import EventBus

ROOT = Path(__file__).resolve().parents[1]
VENTAS_SRC = (ROOT / "modulos" / "ventas.py").read_text(encoding="utf-8")
SALES_SRC = (ROOT / "core" / "services" / "sales_service.py").read_text(encoding="utf-8")
PRINTER_SRC = (ROOT / "core" / "services" / "printer_service.py").read_text(encoding="utf-8")
RESERVATION_SRC = (ROOT / "core" / "services" / "stock_reservation_service.py").read_text(encoding="utf-8")
MP_SRC = (ROOT / "services" / "mercado_pago_service.py").read_text(encoding="utf-8")


def _between(src: str, start: str, end: str) -> str:
    i = src.index(start)
    j = src.index(end, i)
    return src[i:j]


def test_cash_shift_validation_error_blocks_or_warns_explicitly():
    block = _between(VENTAS_SRC, "# ── Validar que la caja esté abierta", "total_a_pagar =")
    assert "logger.exception" in block
    assert "QMessageBox.critical" in block
    assert "return" in block
    assert "pass  # If check fails" not in block


def test_credit_validation_error_not_silent():
    block = _between(VENTAS_SRC, "if is_credit_sale(datos_pago.get('forma_pago')):", "self.finalizar_venta(datos_pago)")
    assert "Validación de crédito falló" in block
    assert "Validación de crédito fallback falló" in block
    assert block.count("QMessageBox.critical") >= 3
    assert "logger.warning(\"validate_credit" not in block


def test_ticket_generation_error_warning_not_pass():
    assert "logger.warning(\"No se pudo generar el ticket HTML" in SALES_SRC
    assert "PrinterService sin EventBus" in PRINTER_SRC
    assert "print_job_log commit failed" in PRINTER_SRC


def test_eventbus_critical_error_not_silent():
    bus = object.__new__(EventBus)
    bus._handlers = {}
    bus._lock = threading.RLock()
    bus._executor = ThreadPoolExecutor(max_workers=1)
    try:
        with pytest.raises(RuntimeError, match="Handlers críticos"):
            bus.publish(SALE_ITEMS_PROCESS, {"sale_id": 1}, strict=True)
    finally:
        bus._executor.shutdown(wait=False)


def test_margin_validation_error_blocks_sale_explicitly():
    block = _between(SALES_SRC, "# Guardia de margen v13.4", "# 2. TRANSACCIÓN CRÍTICA")
    assert "Validación de margen/costo falló" in block
    assert "venta bloqueada" in block
    assert "raise RuntimeError" in block
    assert "pass  # guardia no crítica" not in block


def test_mp_pending_and_reservation_errors_are_logged_not_passed():
    assert "No se pudo persistir intención MP; liberando reserva_id" in SALES_SRC
    assert "Rollback de reserva falló" in RESERVATION_SRC
    assert "MP: no se pudo guardar link de pago" in MP_SRC
    assert "callback post-aprobación falló" in MP_SRC
