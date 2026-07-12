"""Fase G — Endurecimiento born-clean: PK TEXT declaradas NOT NULL.

Riesgo residual documentado (cierre_global.md §6): SQLite NO impone NOT NULL en
una PRIMARY KEY declarada TEXT sin ``NOT NULL`` (a diferencia de ``INTEGER
PRIMARY KEY``, que es alias de ROWID). Un INSERT antiguo que omita ``id`` puede
escribir un id NULL en silencio y romper joins/identidad aguas abajo.

Estos guardrails fijan la mitigación:

  * `test_all_single_column_text_pk_are_not_null` — CERO tolerancia: en el
    schema activo (m000 + cadena completa de migraciones), toda tabla con una
    PRIMARY KEY TEXT de una sola columna debe declararla ``NOT NULL``.
  * `test_insert_null_id_is_rejected_smoke` — test de humo: insertar un id NULL
    (o una fila por DEFAULT VALUES que omita el id) es rechazado por SQLite con
    "NOT NULL constraint failed", en las tablas canónicas de escritura.
"""
from __future__ import annotations

import sqlite3

import pytest


def _active_schema() -> sqlite3.Connection:
    """DB temporal con el bootstrap normal: m000 + toda la cadena de migraciones."""
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    conn = sqlite3.connect(":memory:")
    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()
    return conn


def _single_text_pk_tables(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    """(tabla, columna_pk, notnull) para tablas con PK TEXT de una sola columna.

    PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk).
    """
    out: list[tuple[str, str, int]] = []
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
    for t in tables:
        info = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
        pk_cols = [r for r in info if r[5]]
        if len(pk_cols) == 1 and (pk_cols[0][2] or "").upper() == "TEXT":
            out.append((t, pk_cols[0][1], pk_cols[0][3]))
    return out


def test_all_single_column_text_pk_are_not_null():
    """Toda PK TEXT de una sola columna del schema activo debe ser NOT NULL."""
    conn = _active_schema()
    text_pks = _single_text_pk_tables(conn)
    # El schema born-clean tiene cientos de tablas con id TEXT: sanity check de
    # que realmente estamos midiendo el schema completo, no una DB vacía.
    assert len(text_pks) > 200, (
        f"se esperaban cientos de tablas con PK TEXT, se hallaron {len(text_pks)}")

    nullable = [(t, col) for (t, col, notnull) in text_pks if notnull != 1]
    assert nullable == [], (
        "Fase G: estas tablas tienen PRIMARY KEY TEXT sin NOT NULL — un INSERT "
        "que omita la PK escribiría NULL en silencio. Declara la columna como "
        f"`TEXT NOT NULL PRIMARY KEY` en su migración:\n{nullable}"
    )


@pytest.mark.parametrize("tabla", ["productos", "ventas", "clientes", "sucursales"])
def test_insert_null_id_is_rejected_smoke(tabla):
    """Humo: insertar un id NULL explícito es rechazado por la constraint."""
    conn = _active_schema()
    # Resolver la columna PK real de la tabla.
    info = conn.execute(f'PRAGMA table_info("{tabla}")').fetchall()
    pk = next(r[1] for r in info if r[5])
    with pytest.raises(sqlite3.IntegrityError) as exc:
        conn.execute(f'INSERT INTO "{tabla}" ("{pk}") VALUES (NULL)')
    assert "NOT NULL" in str(exc.value)
    assert f"{tabla}.{pk}" in str(exc.value)


def test_insert_default_values_never_yields_null_pk_smoke():
    """Humo global: para cada tabla con PK TEXT, un INSERT que NO provee la PK
    (DEFAULT VALUES) nunca produce una fila con PK NULL — o SQLite lo rechaza
    (NOT NULL), o inserta un valor. En ningún caso queda un id NULL."""
    conn = _active_schema()
    ofensores: list[str] = []
    for t, pk, _ in _single_text_pk_tables(conn):
        try:
            conn.execute(f'INSERT INTO "{t}" DEFAULT VALUES')
        except sqlite3.IntegrityError:
            conn.rollback()
            continue  # rechazado: comportamiento correcto (NOT NULL u otra)
        except sqlite3.OperationalError:
            conn.rollback()
            continue  # DEFAULT VALUES no soportado por otras columnas: no aplica
        row = conn.execute(
            f'SELECT COUNT(*) FROM "{t}" WHERE "{pk}" IS NULL').fetchone()
        if row[0]:
            ofensores.append(f"{t}.{pk}")
        conn.rollback()
    assert ofensores == [], (
        f"Fase G: estas tablas admitieron una fila con PK NULL: {ofensores}")
