import sys, os, sqlite3
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.services.enterprise.finance_service import FinanceService


def _db_legacy_schema():
    conn = sqlite3.connect(':memory:')
    conn.row_factory = sqlite3.Row
    conn.executescript('''
    CREATE TABLE ventas (id INTEGER PRIMARY KEY, total REAL, estado TEXT, fecha TEXT, sucursal_id INTEGER);
    CREATE TABLE detalles_venta (id INTEGER PRIMARY KEY, venta_id INTEGER, costo_unitario_real REAL, cantidad REAL);
    CREATE TABLE gastos (id INTEGER PRIMARY KEY, monto REAL, fecha TEXT, estado TEXT, monto_pagado REAL);
    CREATE TABLE accounts_payable (id INTEGER PRIMARY KEY, balance REAL, status TEXT, due_date TEXT);
    CREATE TABLE accounts_receivable (id INTEGER PRIMARY KEY, balance REAL, status TEXT);
    CREATE TABLE nomina_pagos (id INTEGER PRIMARY KEY, total REAL, created_at TEXT, estado TEXT);
    CREATE TABLE productos (id INTEGER PRIMARY KEY, existencia REAL, precio_costo REAL);
    CREATE TABLE assets (id INTEGER PRIMARY KEY, valor_actual REAL, estado TEXT, activo INTEGER);
    CREATE TABLE movimientos_caja (id INTEGER PRIMARY KEY, tipo TEXT, monto REAL);
    CREATE TABLE ar_payments (id INTEGER PRIMARY KEY, monto REAL, fecha TEXT);
    CREATE TABLE ap_payments (id INTEGER PRIMARY KEY, monto REAL, fecha TEXT);
    ''')
    conn.executescript('''
    INSERT INTO ventas VALUES (1, 100, 'completada', '2026-04-15', 1);
    INSERT INTO detalles_venta VALUES (1, 1, 40, 1);
    INSERT INTO gastos VALUES (1, 10, '2026-04-15', 'pagado', 10);
    INSERT INTO accounts_payable VALUES (1, 50, 'pendiente', '2026-04-01');
    INSERT INTO accounts_receivable VALUES (1, 25, 'pendiente');
    INSERT INTO nomina_pagos VALUES (1, 20, '2026-04-15', 'pagado');
    INSERT INTO productos VALUES (1, 3, 12);
    INSERT INTO assets VALUES (1, 80, 'activo', 1);
    INSERT INTO movimientos_caja VALUES (1, 'venta', 100);
    INSERT INTO ar_payments VALUES (1, 5, '2026-04-15');
    INSERT INTO ap_payments VALUES (1, 8, '2026-04-15');
    ''')
    conn.commit()
    return conn


def test_finance_service_tolera_schema_legacy_sin_activo_o_costo():
    svc = FinanceService(_db_legacy_schema())
    kpi = svc.dashboard_kpis(branch_id=1, date_from='2026-04-01', date_to='2026-04-30')
    assert kpi['ingresos'] == 100.0
    bal = svc.balance_general(branch_id=1)
    assert bal['activos']['corrientes']['inventario'] > 0
    fc = svc.flujo_caja('2026-04-01', '2026-04-30', branch_id=1)
    assert fc['entradas']['total'] >= 100
