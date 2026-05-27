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
