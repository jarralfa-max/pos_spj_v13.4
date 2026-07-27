import sqlite3

from repositories.cliente_repository import ClienteRepository


def _build_db(with_codigo_fidelidad: bool):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if with_codigo_fidelidad:
        conn.execute(
            """
            CREATE TABLE clientes (
                id INTEGER PRIMARY KEY,
                nombre TEXT,
                telefono TEXT,
                email TEXT,
                codigo_qr TEXT,
                codigo_fidelidad TEXT,
                activo INTEGER DEFAULT 1
            )
            """
        )
        conn.execute(
            "INSERT INTO clientes (id,nombre,telefono,email,codigo_qr,codigo_fidelidad,activo) VALUES (1,'Ana','555','a@a','QR-1','FID-1',1)"
        )
    else:
        conn.execute(
            """
            CREATE TABLE clientes (
                id INTEGER PRIMARY KEY,
                nombre TEXT,
                telefono TEXT,
                email TEXT,
                codigo_qr TEXT,
                activo INTEGER DEFAULT 1
            )
            """
        )
        conn.execute(
            "INSERT INTO clientes (id,nombre,telefono,email,codigo_qr,activo) VALUES (1,'Ana','555','a@a','QR-1',1)"
        )
    conn.commit()
    return conn


def test_busquedas_no_fallan_si_schema_no_tiene_codigo_fidelidad():
    db = _build_db(with_codigo_fidelidad=False)
    repo = ClienteRepository(db)

    by_code = repo.get_by_codigo("555")
    assert by_code is not None
    assert by_code["telefono"] == "555"

    listado = repo.buscar("Ana")
    assert len(listado) == 1
    assert listado[0]["nombre"] == "Ana"

    by_scanner = repo.get_by_scanner("QR-1")
    assert by_scanner is not None
    assert by_scanner["id"] == 1


def test_busquedas_siguen_soportando_codigo_fidelidad_cuando_existe():
    db = _build_db(with_codigo_fidelidad=True)
    repo = ClienteRepository(db)

    by_code = repo.get_by_codigo("FID-1")
    assert by_code is not None
    assert by_code["id"] == 1

    listado = repo.buscar("FID-1")
    assert len(listado) == 1

    by_scanner = repo.get_by_scanner("FID-1")
    assert by_scanner is not None
    assert by_scanner["id"] == 1
