import sqlite3

from core.services.finance.third_party_service import UnifiedThirdPartyService


def _db():
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            rfc TEXT,
            telefono TEXT,
            email TEXT,
            contacto TEXT,
            categoria TEXT,
            direccion TEXT,
            condiciones_pago INTEGER,
            limite_credito REAL,
            banco TEXT,
            notas TEXT,
            activo INTEGER DEFAULT 1
        )
    """)
    conn.execute("""
        CREATE TABLE accounts_payable (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            supplier_id INTEGER,
            status TEXT,
            balance REAL
        )
    """)
    conn.commit()
    return conn


def test_get_all_proveedores_devuelve_dicts():
    db = _db()
    db.execute(
        "INSERT INTO proveedores(nombre, contacto, activo) VALUES ('Proveedor A','Juan',1)"
    )
    db.execute(
        "INSERT INTO accounts_payable(supplier_id, status, balance) VALUES (1, 'pendiente', 250.0)"
    )
    db.commit()

    svc = UnifiedThirdPartyService(db)
    rows = svc.get_all_proveedores(activo=True, limit=50)

    assert len(rows) == 1
    assert rows[0]["nombre"] == "Proveedor A"
    assert float(rows[0]["saldo_pendiente"]) == 250.0


def test_create_y_get_proveedor():
    db = _db()
    svc = UnifiedThirdPartyService(db)

    pid = svc.create_proveedor({"nombre": "Proveedor B", "telefono": "+525511112222"})
    item = svc.get_proveedor(pid)

    assert item is not None
    assert item["id"] == pid
    assert item["nombre"] == "Proveedor B"
