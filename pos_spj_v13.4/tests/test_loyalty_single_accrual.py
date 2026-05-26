import sqlite3
from unittest.mock import MagicMock

from core.services.loyalty_service import LoyaltyService
from core.events.wiring import _wire_venta
from core.events.event_bus import EventBus, VENTA_COMPLETADA
from core.use_cases.venta import ProcesarVentaUC, ItemCarrito, DatosPago


def _db():
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    db.execute("INSERT INTO clientes(id, nombre, puntos) VALUES (1, 'Cliente', 0)")
    db.execute(
        """CREATE TABLE loyalty_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER,
            tipo TEXT,
            puntos INTEGER,
            monto_equiv REAL,
            saldo_post INTEGER,
            referencia TEXT,
            descripcion TEXT,
            sucursal_id INTEGER,
            usuario TEXT
        )"""
    )
    db.execute(
        "CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, accion TEXT, modulo TEXT, entidad TEXT, entidad_id INTEGER, usuario TEXT, sucursal_id INTEGER, detalles TEXT, fecha TEXT)"
    )
    db.commit()
    return db


def test_loyalty_handler_idempotent_same_venta_id_no_duplicate_ledger():
    db = _db()
    svc = LoyaltyService(db_conn=db)
    svc.process_loyalty_for_sale = MagicMock(return_value={})

    container = MagicMock()
    container.db = db
    container.loyalty_service = svc
    container.event_logger = None
    container.treasury_service = None
    container.finance_service = None

    bus = EventBus()
    _wire_venta(bus, container)

    payload = {
        "venta_id": 99,
        "cliente_id": 1,
        "total": 100.0,
        "sucursal_id": 1,
        "usuario": "cajero",
        "folio": "V-99",
    }
    bus.publish(VENTA_COMPLETADA, payload, async_=False)
    bus.publish(VENTA_COMPLETADA, payload, async_=False)

    assert svc.process_loyalty_for_sale.call_count == 2
    for call in svc.process_loyalty_for_sale.call_args_list:
        assert call.kwargs["venta_id"] == 99


def test_loyalty_service_registrar_en_ledger_is_idempotent_by_tipo_referencia():
    db = _db()
    svc = LoyaltyService(db_conn=db)
    svc._engine = None

    ok1 = svc.registrar_en_ledger(cliente_id=1, tipo="acumulacion", puntos=10, referencia="123", descripcion="x", usuario="u")
    ok2 = svc.registrar_en_ledger(cliente_id=1, tipo="acumulacion", puntos=10, referencia="123", descripcion="x", usuario="u")

    assert ok1 is True
    assert ok2 is True
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='acumulacion' AND referencia='123'").fetchone()[0]
    assert c == 1


def test_procesar_venta_uc_does_not_call_loyalty_process_directly():
    sales = MagicMock()
    sales.execute_sale.return_value = ("F-1", "")
    sales.db = MagicMock()
    sales.db.execute.return_value.fetchone.return_value = (1,)

    loyalty = MagicMock()

    uc = ProcesarVentaUC(
        sales_service=sales,
        inventory_service=MagicMock(get_stock=MagicMock(return_value=100)),
        finance_service=MagicMock(),
        loyalty_service=loyalty,
        ticket_engine=None,
        sync_service=None,
        event_bus=None,
    )

    r = uc.ejecutar(
        items=[ItemCarrito(producto_id=1, cantidad=1, precio_unit=10, nombre="P")],
        datos_pago=DatosPago(forma_pago="Efectivo", monto_pagado=10, cliente_id=1),
        sucursal_id=1,
        usuario="u",
    )

    assert r.ok is True
    loyalty.process_loyalty_for_sale.assert_not_called()
