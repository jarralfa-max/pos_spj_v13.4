import importlib.util
import py_compile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

from application.services.loyalty_application_service import LoyaltyApplicationService
from core.events.event_bus import EventBus, VENTA_COMPLETADA
from core.events.wiring import _wire_venta
from core.services.sales_service import SalesService
from core.services.loyalty_service import LoyaltyService

ROOT = Path(__file__).resolve().parents[1]


def _db_basic():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, tipo TEXT, puntos INTEGER, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0, referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id INTEGER DEFAULT 1, usuario TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), UNIQUE(cliente_id,tipo,referencia))")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, puntos INTEGER DEFAULT 0)")
    db.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    db.execute("CREATE TABLE loyalty_pasivo_log (id INTEGER PRIMARY KEY AUTOINCREMENT, fecha TEXT, tipo TEXT, estrellas INTEGER, valor_unitario REAL, monto_total REAL, referencia TEXT, sucursal_id INTEGER)")
    db.execute("INSERT INTO clientes(id,nombre,puntos) VALUES (1,'Ana',0)")
    return db


def test_award_points_idempotent():
    db = _db_basic()
    svc = LoyaltyApplicationService(db)
    svc.award_points_for_sale(cliente_id=1, venta_id='V-1', puntos=20)
    svc.award_points_for_sale(cliente_id=1, venta_id='V-1', puntos=20)
    saldo = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert saldo == 20


def test_acumulacion_idempotente_loyalty_service():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls.acreditar_venta(cliente_id=1, venta_id='V-ACU-1', cajero='u', total=100.0)
    ls.acreditar_venta(cliente_id=1, venta_id='V-ACU-1', cajero='u', total=100.0)
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='acumulacion' AND referencia='V-ACU-1'").fetchone()[0]
    assert c == 1


def test_redeem_points_idempotent():
    db = _db_basic()
    svc = LoyaltyApplicationService(db)
    svc.award_points_for_sale(cliente_id=1, venta_id='V-1', puntos=100)
    svc.redeem_points_for_sale(cliente_id=1, venta_id='V-2', puntos=30)
    svc.redeem_points_for_sale(cliente_id=1, venta_id='V-2', puntos=30)
    saldo = db.execute("SELECT COALESCE(SUM(puntos),0) FROM loyalty_ledger WHERE cliente_id=1").fetchone()[0]
    assert saldo == 70


def test_canje_idempotente_loyalty_service():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls.acreditar_venta(cliente_id=1, venta_id='V-CAN-BASE', cajero='u', total=1000.0)
    ls.canjear(cliente_id=1, cajero_id=1, subtotal=1000.0, estrellas=20, venta_id=99)
    ls.canjear(cliente_id=1, cajero_id=1, subtotal=1000.0, estrellas=20, venta_id=99)
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='canje' AND referencia='99'").fetchone()[0]
    assert c == 1


def test_sales_redemption_inside_transaction():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, folio TEXT, operation_id TEXT)")
    db.execute("CREATE TABLE loyalty_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, tipo TEXT, puntos INTEGER, referencia TEXT, UNIQUE(cliente_id,tipo,referencia))")
    sales_repo = MagicMock()
    sales_repo.create_sale.return_value = (10, 'F-10')
    sales_repo.save_sale_item.return_value = None
    loyalty = MagicMock()
    loyalty.compute_redemption_discount.return_value = 0.0
    loyalty.apply_redemption.return_value = {"ok": False, "error": "boom"}
    svc = SalesService(
        db_conn=db, sales_repo=sales_repo, recipe_repo=MagicMock(), inventory_service=MagicMock(),
        finance_service=MagicMock(), loyalty_service=loyalty, promotion_engine=None, sync_service=None,
        ticket_template_engine=MagicMock(), whatsapp_service=MagicMock(),
        config_service=MagicMock(get=MagicMock(return_value='<html>{{folio}}</html>')),
        feature_flag_service=MagicMock(), customer_service=MagicMock(get_customer=MagicMock(return_value={"id":1}), validate_credit=MagicMock(return_value=(True,""))),
    )
    svc._validate_stock_pre_sale = MagicMock()
    svc._resolve_sale_items = MagicMock(return_value=[])
    bus = EventBus()
    original = bus.publish
    bus.publish = lambda *a, **k: None
    try:
        try:
            svc.execute_sale(branch_id=1, user='u', items=[{"product_id":1,"qty":1,"unit_price":10}], payment_method='Efectivo', amount_paid=10, client_id=1, loyalty_redemption_pts=10)
            assert False, 'expected failure'
        except RuntimeError:
            pass
    finally:
        bus.publish = original
    assert loyalty.apply_redemption.called


def test_birthday_config_save_load():
    db = _db_basic()
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES ('ref_bono_referidor','50')")
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES ('ref_bono_referido','25')")
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES ('ref_max_mensual','10')")
    ls = LoyaltyService(db)
    ls.save_birthday_config(123, 'Hola {nombre}')
    cfg = ls.get_birthday_config()
    assert cfg['cumple_bono_estrellas'] == '123'
    assert cfg['cumple_mensaje_wa'] == 'Hola {nombre}'
    ref = ls.get_referral_config()
    assert ref['ref_bono_referidor'] == 50 and ref['ref_bono_referido'] == 25 and ref['ref_max_mensual'] == 10


def test_cumpleanios_no_toca_referidos():
    db = _db_basic()
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES ('ref_bono_referidor','77')")
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES ('ref_bono_referido','33')")
    db.execute("INSERT INTO configuraciones(clave,valor) VALUES ('ref_max_mensual','12')")
    ls = LoyaltyService(db)
    ls.save_birthday_config(111, 'Msg cumple')
    ref = ls.get_referral_config()
    assert ref['ref_bono_referidor'] == 77 and ref['ref_bono_referido'] == 33 and ref['ref_max_mensual'] == 12


def test_loyalty_event_skip_if_already_processed():
    db = _db_basic()
    container = type('C', (), {})()
    container.db = db
    container.sync_service = None
    container.loyalty_service = MagicMock()
    container.finance_service = None
    bus = EventBus()
    bus.clear_handlers()
    _wire_venta(bus, container)
    bus.publish(VENTA_COMPLETADA, {"cliente_id": 1, "total": 100, "venta_id": 1, "sucursal_id": 1, "usuario": "u", "loyalty_already_processed": True}, async_=False)
    container.loyalty_service.process_loyalty_for_sale.assert_not_called()


def test_growth_engine_ui_compiles():
    py_compile.compile(str(ROOT / 'modulos' / 'modulo_growth_engine.py'), doraise=True)


def test_no_ui_private_repo_access():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert '_app.repo' not in src
