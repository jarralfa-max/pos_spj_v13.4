import sqlite3

from repositories.loyalty_repository import LoyaltyRepository


def _db():
    db = sqlite3.connect(':memory:')
    db.execute("CREATE TABLE loyalty_ledger (id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER, tipo TEXT, puntos INTEGER, monto_equiv REAL DEFAULT 0, saldo_post INTEGER DEFAULT 0, referencia TEXT DEFAULT '', descripcion TEXT DEFAULT '', sucursal_id INTEGER DEFAULT 1, usuario TEXT DEFAULT '', created_at TEXT DEFAULT (datetime('now')), UNIQUE(cliente_id,tipo,referencia))")
    db.execute("CREATE TABLE clientes (id INTEGER PRIMARY KEY, nombre TEXT, telefono TEXT, puntos INTEGER DEFAULT 0, fecha_nacimiento TEXT, activo INTEGER DEFAULT 1)")
    db.execute("CREATE TABLE ventas (id INTEGER PRIMARY KEY, cliente_id INTEGER, fecha TEXT, total REAL)")
    db.execute("CREATE TABLE configuraciones (clave TEXT PRIMARY KEY, valor TEXT)")
    db.execute("CREATE TABLE tarjetas_fidelidad (id INTEGER PRIMARY KEY, codigo TEXT, cliente_id INTEGER, id_cliente INTEGER, estado TEXT, nivel TEXT, puntos_actuales INTEGER DEFAULT 0, puntos INTEGER DEFAULT 0)")
    return db


def test_referral_config_and_referrals_and_at_risk_and_birthdays():
    db = _db()
    repo = LoyaltyRepository(db)

    repo.save_referral_config(60, 30, 9)
    cfg = repo.get_referral_config()
    assert cfg['ref_bono_referidor'] == 60
    assert cfg['ref_bono_referido'] == 30
    assert cfg['ref_max_mensual'] == 9

    db.execute("INSERT INTO clientes(id,nombre,telefono,puntos,fecha_nacimiento,activo) VALUES (1,'Ana','555',0,date('now','+1 day'),1)")
    db.execute("INSERT INTO clientes(id,nombre,telefono,puntos,fecha_nacimiento,activo) VALUES (2,'Beto','777',0,date('now','+2 day'),1)")
    repo.list_referrals()  # crea tabla referidos si no existe
    db.execute("INSERT INTO referidos(referidor_id,referido_id,bono_dado,estado) VALUES (1,2,25,'pagado')")
    db.execute("INSERT INTO ventas(cliente_id,fecha,total) VALUES (1, datetime('now','-45 day'), 123.45)")

    birthdays = repo.list_upcoming_birthdays(7)
    assert len(birthdays) >= 2

    referrals = repo.list_referrals()
    assert len(referrals) == 1

    risk = repo.list_at_risk_customers(30)
    assert any((r[0] if isinstance(r, tuple) else r['nombre']) == 'Ana' for r in risk)


def test_card_assign_block_and_ledger_summary():
    db = _db()
    repo = LoyaltyRepository(db)
    db.execute("INSERT INTO clientes(id,nombre,telefono,puntos) VALUES (1,'Ana','555',10)")
    db.execute("INSERT INTO tarjetas_fidelidad(id,codigo,cliente_id,id_cliente,estado,nivel,puntos_actuales,puntos) VALUES (10,'CARD1',NULL,NULL,'nueva','Bronce',0,0)")

    assert repo.append_ledger_entry(cliente_id=1, tipo='acumulacion', puntos=100, referencia='V1') is True
    assert repo.append_ledger_entry(cliente_id=1, tipo='acumulacion', puntos=100, referencia='V1') is False
    summary = repo.get_customer_summary(1)
    assert summary['saldo_ledger'] == 100

    repo.assign_card(1, 'CARD1')
    card = repo.get_card_by_code('CARD1')
    assert card['cliente_id'] == 1
    repo.block_card('CARD1')
    card2 = repo.get_card_by_code('CARD1')
    assert card2['estado'] == 'bloqueada'
