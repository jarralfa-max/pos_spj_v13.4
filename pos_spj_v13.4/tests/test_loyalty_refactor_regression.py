import importlib.util
import py_compile
import sqlite3
import re
from pathlib import Path
from unittest.mock import MagicMock

from application.services.loyalty_application_service import LoyaltyApplicationService
from core.events.event_bus import EventBus, VENTA_COMPLETADA
from core.events.wiring import _wire_venta
from core.services.sales_service import SalesService
from core.services.loyalty_service import LoyaltyService
from repositories.loyalty_repository import LoyaltyRepository

ROOT = Path(__file__).resolve().parents[1]


def _db_basic():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0, referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id TEXT, usuario TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), UNIQUE(cliente_id,tipo,referencia))")
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
    db.execute("CREATE TABLE loyalty_ledger (id TEXT PRIMARY KEY, cliente_id TEXT, tipo TEXT, puntos INTEGER, referencia TEXT, UNIQUE(cliente_id,tipo,referencia))")
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


def test_acreditar_venta_no_duplica_evento_financiero():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls._publish_loyalty_fin_event = MagicMock()
    ls._publish_puntos = MagicMock()
    ls.acreditar_venta(cliente_id=1, venta_id='V-DUP', cajero='u', total=100.0)
    ls.acreditar_venta(cliente_id=1, venta_id='V-DUP', cajero='u', total=100.0)
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='acumulacion' AND referencia='V-DUP'").fetchone()[0]
    assert c == 1
    assert ls._publish_loyalty_fin_event.call_count == 1
    assert ls._publish_puntos.call_count == 1


def test_canjear_no_duplica_evento_financiero():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls.acreditar_venta(cliente_id=1, venta_id='BASE', cajero='u', total=1000.0)
    ls._publish_loyalty_fin_event = MagicMock()
    ls.canjear(cliente_id=1, cajero_id=1, subtotal=500.0, estrellas=10, venta_id=123)
    ls.canjear(cliente_id=1, cajero_id=1, subtotal=500.0, estrellas=10, venta_id=123)
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='canje' AND referencia='123'").fetchone()[0]
    assert c == 1
    assert ls._publish_loyalty_fin_event.call_count == 1


def test_reversar_canje_no_duplica_evento_financiero():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls.acreditar_venta(cliente_id=1, venta_id='V-REV-EVT-BASE', cajero='u', total=1000.0)
    ls.canjear(cliente_id=1, cajero_id=1, subtotal=1000.0, estrellas=15, venta_id='V-REV-EVT-1')
    ls._publish_loyalty_fin_event = MagicMock()
    ls.reversar_canje(cliente_id=1, puntos_canjeados=15, referencia='V-REV-EVT-1', usuario='u')
    ls.reversar_canje(cliente_id=1, puntos_canjeados=15, referencia='V-REV-EVT-1', usuario='u')
    c = db.execute("SELECT COUNT(*) FROM loyalty_ledger WHERE cliente_id=1 AND tipo='reversa' AND referencia='reversa:V-REV-EVT-1'").fetchone()[0]
    assert c == 1
    assert ls._publish_loyalty_fin_event.call_count == 1


def test_growth_engine_carga_loyalty_y_fallback_growth_claves():
    src = (ROOT / 'modulos' / 'modulo_growth_engine.py').read_text(encoding='utf-8')
    assert 'def _cargar_config(self):' in src
    assert 'cfg.get("loyalty_expiry_dias", cfg.get("growth_expiry_dias", "90"))' in src
    assert 'cfg.get("loyalty_otp_umbral", cfg.get("growth_otp_umbral", "200"))' in src
    assert 'cfg.get("loyalty_valor_estrella", cfg.get("growth_costo_estrella", "0.80"))' in src
    assert 'cfg.get("loyalty_max_pct_canje", cfg.get("growth_cap_pct", "0.50"))' in src


def test_growth_engine_guardado_sigue_en_claves_canonicas_loyalty():
    src = (ROOT / 'modulos' / 'modulo_growth_engine.py').read_text(encoding='utf-8')
    assert '"loyalty_expiry_dias"' in src
    assert '"loyalty_otp_umbral"' in src
    assert '"loyalty_valor_estrella"' in src
    assert '"loyalty_max_pct_canje"' in src


def test_pasivo_operativo_desde_ledger_es_canonico():
    db = _db_basic()
    ls = LoyaltyService(db)
    ls.acreditar_venta(cliente_id=1, venta_id='V-PASIVO-1', cajero='u', total=100.0)  # +10
    ls.canjear(cliente_id=1, cajero_id=1, subtotal=500.0, estrellas=4, venta_id=901)  # -4
    res = ls.pasivo_operativo_desde_ledger()
    assert res["total_estrellas"] == 6
    assert abs(res["valor_monetario"] - 0.6) < 1e-9


def test_loyalty_repository_aisla_ddl_referidos_en_ensure():
    src = (ROOT / 'repositories' / 'loyalty_repository.py').read_text(encoding='utf-8')
    assert 'def ensure_referrals_table(self) -> None:' in src
    assert 'def list_referrals(self, limit: int = 50) -> List[Any]:' in src
    assert 'self.ensure_referrals_table()' in src
    # list_referrals no debe mezclar DDL inline; el CREATE se mantiene aislado en ensure_*.
    list_block = src.split('def list_referrals(self, limit: int = 50) -> List[Any]:', 1)[1].split('def ensure_referrals_table(self) -> None:', 1)[0]
    assert 'CREATE TABLE IF NOT EXISTS referidos' not in list_block


def test_fidelidad_config_no_hardcodea_qfont_arial():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert 'QFont("Arial"' not in src
    assert 'font = it.font()' in src
    assert 'font.setBold(True)' in src


def test_loyalty_dashboard_kpis_shape():
    db = _db_basic()
    db.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY, cliente_id INTEGER, fecha TEXT, total REAL)")
    db.execute("CREATE TABLE tarjetas_fidelidad (id INTEGER PRIMARY KEY, id_cliente INTEGER, cliente_id INTEGER, nivel TEXT)")
    ls = LoyaltyService(db)
    kpis = ls.get_dashboard_kpis()
    expected = {
        "clientes_con_puntos",
        "puntos_activos",
        "pasivo_operativo",
        "puntos_emitidos_mes",
        "puntos_canjeados_mes",
        "cumples_7_dias",
        "clientes_en_riesgo",
        "rifas_activas",
    }
    assert expected.issubset(set(kpis.keys()))
    assert isinstance(kpis["pasivo_operativo"], float)
    for key in expected - {"pasivo_operativo"}:
        assert isinstance(kpis[key], int)


def test_fidelidad_config_no_private_repo_access():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert "_app.repo" not in src


def test_fidelidad_ui_no_qfont_arial():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert 'QFont("Arial"' not in src


def test_growth_ui_no_hex_styles():
    src = (ROOT / 'modulos' / 'modulo_growth_engine.py').read_text(encoding='utf-8')
    assert 'setStyleSheet("' not in src or "#" not in src
    assert 'QColor("#' not in src
    assert 'Qt.darkGreen' not in src
    assert "style='color:" not in src
    assert "style='font-size:" not in src


def test_fidelidad_ui_no_visual_hardcodes():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert 'QColor("#' not in src
    assert 'QFont("Arial"' not in src
    assert "style='color:" not in src
    assert "style='font-size:" not in src


def test_raffle_tables_ensure_and_list():
    db = _db_basic()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()
    rows = repo.list_raffles(limit=10)
    assert rows == []


def test_raffle_tables_have_required_columns():
    db = _db_basic()
    repo = LoyaltyRepository(db)
    repo.ensure_raffle_tables()

    def _cols(table_name: str) -> set:
        return {r[1] for r in db.execute(f"PRAGMA table_info({table_name})").fetchall()}

    assert {
        "id", "nombre", "descripcion", "premio", "estado",
        "fecha_inicio", "fecha_fin", "monto_por_boleto",
        "max_boletos_por_cliente", "sucursal_id", "created_at", "updated_at",
    }.issubset(_cols("raffles"))
    assert {
        "id", "raffle_id", "cliente_id", "venta_id", "folio_venta",
        "numero_boleto", "monto_base", "estado", "sucursal_id", "created_at",
    }.issubset(_cols("raffle_tickets"))
    assert {
        "id", "raffle_id", "ticket_id", "cliente_id", "premio",
        "seleccionado_por", "fecha_seleccion", "notificado",
    }.issubset(_cols("raffle_winners"))


def test_event_bus_has_raffle_events():
    src = (ROOT / 'core' / 'events' / 'event_bus.py').read_text(encoding='utf-8')
    assert "RAFFLE_CREATED" in src
    assert "RAFFLE_ACTIVATED" in src
    assert "RAFFLE_TICKET_GRANTED" in src
    assert "RAFFLE_CLOSED" in src
    assert "RAFFLE_WINNER_SELECTED" in src


def test_fidelidad_raffles_tab_ui_scaffold():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert '🎟️ Rifas y Sorteos' in src
    assert 'create_kpi_bar(' in src
    assert 'list_raffles(limit=50)' in src
    assert 'get_raffle_summary()' in src


def test_wiring_raffle_flow_hooked_to_venta_completada_phase4():
    src = (ROOT / 'core' / 'events' / 'wiring.py').read_text(encoding='utf-8')
    venta_block = src.split("def _wire_venta", 1)[1]
    assert "process_raffles_for_sale" in venta_block
    assert "raffle_already_processed" in venta_block
    assert "cancel_tickets_for_sale" in venta_block


# FASE 7 — nombres canónicos solicitados
def test_fidelidad_config_no_private_repo_access():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert "_app.repo" not in src


def test_fidelidad_ui_no_qfont_arial():
    src = (ROOT / 'modulos' / 'fidelidad_config.py').read_text(encoding='utf-8')
    assert 'QFont("Arial"' not in src


def test_growth_ui_no_hex_styles():
    src = (ROOT / 'modulos' / 'modulo_growth_engine.py').read_text(encoding='utf-8')
    # Solo bloquear estilo inline con hex dentro de setStyleSheet.
    assert re.search(r'setStyleSheet\([^\)]*#[0-9a-fA-F]{3,8}', src) is None
