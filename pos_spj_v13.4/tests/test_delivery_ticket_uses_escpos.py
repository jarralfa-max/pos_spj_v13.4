import sqlite3
from core.services.ticket_printer_service import TicketPrinterService


class _Printer:
    def __init__(self):
        self.calls = []
    def has_ticket_printer(self):
        return True
    def print_ticket(self, data):
        self.calls.append(data)
        return "job-1"


def _db():
    c = sqlite3.connect(':memory:')
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE delivery_orders(id INTEGER, folio TEXT, cliente_nombre TEXT, cliente_tel TEXT, direccion TEXT, notas TEXT, pago_metodo TEXT, total REAL, costo_envio REAL, estado TEXT, fecha TEXT, driver_id INTEGER, tiempo_estimado INTEGER)')
    c.execute('CREATE TABLE drivers(id INTEGER, nombre TEXT)')
    c.execute('CREATE TABLE delivery_items(id INTEGER, delivery_id INTEGER, nombre TEXT, cantidad REAL, precio_unitario REAL, subtotal REAL, unidad TEXT, prepared_qty REAL, tolerance_exceeded INTEGER)')
    c.execute("INSERT INTO drivers VALUES(1,'R1')")
    c.execute("INSERT INTO delivery_orders VALUES(1,'D-1','C1','555','Dir','N','Efectivo',100,0,'nuevo','2026-01-01',1,30)")
    c.execute("INSERT INTO delivery_items VALUES(1,1,'Prod',1,100,100,'u',1,0)")
    c.commit()
    return c


def test_delivery_cliente_y_repartidor_usan_printerservice():
    p = _Printer()
    svc = TicketPrinterService(_db(), printer_service=p)
    assert svc.print_customer_ticket(1) is True
    assert svc.print_driver_ticket(1) is True
    assert len(p.calls) == 2
    assert p.calls[0].get('ticket_type') == 'delivery_customer'
    assert p.calls[1].get('ticket_type') == 'delivery_driver'
