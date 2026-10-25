"""Contrato transaccional de TODAS las unidades de trabajo (ADR-006, Slice 0
de la arquitectura híbrida; cierra R-01 y R-02 del registro de riesgos).

R-01: con el pool en autocommit (`connection.py`) cada sentencia se confirmaba
sola y el rollback de una UoW no deshacía nada; con la conexión del escritorio
sí. Ahora el resultado no depende de la conexión: se prueba con las DOS
conexiones reales de la app y con cada UoW descubierta en disco.

R-02: la conexión del escritorio corría con llaves foráneas apagadas.
"""

from __future__ import annotations

import glob
import importlib
import inspect
import os
import sqlite3

import pytest

from backend.infrastructure.db.transaction import TransactionalUnitOfWork

_RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


def _unidades():
    clases = []
    for ruta in sorted(glob.glob(os.path.join(
            _RAIZ, "backend", "infrastructure", "db", "repositories", "*", "unit_of_work.py"))):
        modulo = importlib.import_module(
            os.path.relpath(ruta, _RAIZ)[:-3].replace(os.sep, "."))
        clases += [c for _, c in inspect.getmembers(modulo, inspect.isclass)
                   if c.__module__ == modulo.__name__ and c.__name__.endswith("UnitOfWork")]
    from backend.infrastructure.db.unit_of_work import ConnectionUnitOfWork
    return clases + [ConnectionUnitOfWork]


UNIDADES = _unidades()
_RUTAS: dict[int, str] = {}   # archivo de cada conexión de prueba


def test_every_unit_of_work_uses_the_shared_boundary():
    """Una sola regla: ninguna UoW vuelve a implementar su propio commit."""
    assert len(UNIDADES) >= 20
    propias = [c.__name__ for c in UNIDADES if not issubclass(c, TransactionalUnitOfWork)
               or any(m in vars(c) for m in ("__enter__", "__exit__", "commit", "rollback"))]
    assert propias == []


def _escritorio(path):
    """La conexión del escritorio: `DatabaseIntegrityStep` (transacciones implícitas)."""
    return sqlite3.connect(path)


def _pool(path):
    """La conexión del pool: `connection._new_connection` (autocommit, WAL, FK ON)."""
    from backend.infrastructure.db import connection as pool
    return pool._new_connection(path)


@pytest.fixture(params=["escritorio", "pool"])
def conn(request, tmp_path):
    path = str(tmp_path / "uow.db")
    abrir = _escritorio if request.param == "escritorio" else _pool
    c = abrir(path)
    c.execute("CREATE TABLE t (x TEXT)")
    if c.in_transaction:
        c.commit()
    _RUTAS[id(c)] = path
    yield c
    c.close()


def _filas_vistas_por_otra_conexion(conn) -> int:
    otra = sqlite3.connect(_RUTAS[id(conn)])
    try:
        return otra.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    finally:
        otra.close()


def _nueva(cls, conn, **kw):
    try:
        return cls(conn, **kw)
    except TypeError:
        if kw:
            pytest.skip(f"{cls.__name__} no acepta {kw}")
        raise


@pytest.mark.parametrize("cls", UNIDADES, ids=lambda c: c.__name__)
def test_failure_rolls_back_on_both_connections(cls, conn):
    with pytest.raises(RuntimeError):
        with _nueva(cls, conn):
            conn.execute("INSERT INTO t VALUES ('a')")
            conn.execute("INSERT INTO t VALUES ('b')")
            raise RuntimeError("falla a mitad")
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    assert not conn.in_transaction


@pytest.mark.parametrize("cls", UNIDADES, ids=lambda c: c.__name__)
def test_success_is_durable_on_both_connections(cls, conn):
    with _nueva(cls, conn):
        conn.execute("INSERT INTO t VALUES ('a')")
    assert _filas_vistas_por_otra_conexion(conn) == 1
    assert not conn.in_transaction


def test_nested_unit_rolls_back_only_its_own_writes(conn):
    from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork
    from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork

    with SalesUnitOfWork(conn):
        conn.execute("INSERT INTO t VALUES ('venta')")
        try:
            with FinanceUnitOfWork(conn):
                conn.execute("INSERT INTO t VALUES ('asiento')")
                raise ValueError("el asiento falla")
        except ValueError:
            pass
        assert conn.in_transaction   # la anidada NO confirmó la de afuera
    assert [r[0] for r in conn.execute("SELECT x FROM t")] == ["venta"]
    assert _filas_vistas_por_otra_conexion(conn) == 1


def test_nested_success_waits_for_the_outer_unit(conn):
    from backend.infrastructure.db.repositories.inventory.unit_of_work import (
        InventoryUnitOfWork,
    )
    from backend.infrastructure.db.repositories.sales.unit_of_work import SalesUnitOfWork

    with pytest.raises(RuntimeError):
        with SalesUnitOfWork(conn):
            with InventoryUnitOfWork(conn):
                conn.execute("INSERT INTO t VALUES ('existencia')")
            assert _filas_vistas_por_otra_conexion(conn) == 0
            raise RuntimeError("la venta falla después")
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_unit_that_does_not_own_the_transaction_never_touches_it(conn):
    from backend.infrastructure.db.repositories.inventory.unit_of_work import (
        InventoryUnitOfWork,
    )

    conn.execute("BEGIN")
    with InventoryUnitOfWork(conn, owns_transaction=False):
        conn.execute("INSERT INTO t VALUES ('x')")
    assert conn.in_transaction
    conn.rollback()
    assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_cash_register_unit_still_rejects_a_second_commit(conn):
    from backend.infrastructure.db.repositories.cash_register.unit_of_work import (
        CashRegisterUnitOfWork,
    )

    with CashRegisterUnitOfWork(conn) as uow:
        conn.execute("INSERT INTO t VALUES ('x')")
        uow.commit()
        with pytest.raises(RuntimeError, match="already completed"):
            uow.commit()


def test_sequential_units_on_the_same_connection_are_independent(conn):
    from backend.infrastructure.db.repositories.loyalty.unit_of_work import LoyaltyUnitOfWork

    with LoyaltyUnitOfWork(conn):
        conn.execute("INSERT INTO t VALUES ('1')")
    with pytest.raises(KeyError):
        with LoyaltyUnitOfWork(conn):
            conn.execute("INSERT INTO t VALUES ('2')")
            raise KeyError
    assert _filas_vistas_por_otra_conexion(conn) == 1


# ── R-02: llaves foráneas en la conexión del escritorio ─────────────────────
def _con_llaves(tmp_path, huerfano: bool):
    c = sqlite3.connect(str(tmp_path / "fk.db"))
    c.executescript("CREATE TABLE padre (id TEXT PRIMARY KEY);"
                    "CREATE TABLE hijo (id TEXT PRIMARY KEY, padre_id TEXT REFERENCES padre(id));"
                    "INSERT INTO padre VALUES ('p');")
    c.execute("INSERT INTO hijo VALUES ('h', ?)", ("nadie" if huerfano else "p",))
    c.commit()
    return c


def test_foreign_keys_are_enforced_after_migrating_when_the_data_complies(tmp_path):
    from backend.bootstrap.steps.foreign_key_enforcement_step import enable_foreign_keys

    c = _con_llaves(tmp_path, huerfano=False)
    assert enable_foreign_keys(c) == []
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO hijo VALUES ('h2', 'nadie')")


def test_orphans_keep_the_pos_opening_and_are_reported(tmp_path):
    from backend.bootstrap.bootstrap_severity import BootstrapSeverity
    from backend.bootstrap.steps.foreign_key_enforcement_step import ForeignKeyEnforcementStep

    c = _con_llaves(tmp_path, huerfano=True)
    contexto = type("Ctx", (), {"conn": c})()
    resultado = ForeignKeyEnforcementStep().run(contexto)
    assert resultado.success and resultado.severity is BootstrapSeverity.WARNING
    assert "hijo (1)" in resultado.message
    assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 0
