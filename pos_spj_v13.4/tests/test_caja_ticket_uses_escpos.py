from core.services.caja_ticket_service import CajaTicketService


class _Printer:
    def __init__(self):
        self.calls = []
    def has_ticket_printer(self):
        return True
    def print_ticket(self, data):
        self.calls.append(data)
        return 'job-z'


def test_caja_corte_usa_printerservice():
    p = _Printer()
    svc = CajaTicketService(printer_service=p)
    ok = svc.enviar_escpos({'cierre_id': 9, 'fecha': '2026-01-01', 'cajero': 'ana', 'ventas_totales': 100, 'diferencia': 0})
    assert ok is True
    assert len(p.calls) == 1
    assert p.calls[0].get('ticket_type') == 'caja_corte_z'


def test_preview_or_print_corte_auto_prints(caplog):
    """Bug 4: el corte Z se auto-imprime al generarse (sin pulsar botón).

    Headless: la parte de vista previa (PyQt) puede no estar disponible;
    el envío térmico ocurre antes y no depende de la UI.
    """
    p = _Printer()
    svc = CajaTicketService(printer_service=p)
    svc.preview_or_print_corte(
        {'cierre_id': 'z-1', 'total_ventas': 250.0, 'efectivo_contado': 250.0,
         'efectivo_esperado': 250.0, 'diferencia': 0.0, 'fondo_inicial': 100.0},
        cajero='ana',
    )
    assert len(p.calls) == 1
    assert p.calls[0].get('ticket_type') == 'caja_corte_z'
    assert p.calls[0].get('folio') == 'Z-z-1'


class _PrinterOffline:
    def has_ticket_printer(self):
        return False


def test_preview_or_print_corte_survives_missing_printer():
    """Sin impresora térmica no truena: sigue al PDF/preview sin propagar."""
    svc = CajaTicketService(printer_service=_PrinterOffline())
    svc.preview_or_print_corte({'cierre_id': 'z-2', 'total_ventas': 10.0}, cajero='ana')
