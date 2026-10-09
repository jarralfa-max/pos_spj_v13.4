"""308 — diferencias de caja con DOS personas: el responsable explica; otra revisa y resuelve.

POR QUÉ (decisión del usuario, 2026-10-07)
-----------------------------------------
`cash_differences` exigía TRES personas distintas: quien generó el Corte Z no
podía revisar, y quien revisaba no podía resolver. Con los dos usuarios reales
de la instalación una diferencia jamás podía resolverse, y además un gerente
que generaba el Corte Z por el cajero quedaba impedido de revisarla.

Regla nueva (se conserva §46: el cajero nunca resuelve su propia diferencia):
* revisa y resuelve alguien distinto del RESPONSABLE (el cajero del turno) y de
  quien la explicó;
* quien revisó PUEDE resolver.

Los CHECK de SQLite no se alteran en sitio: la tabla se reconstruye con el DDL
de la 175 (ya corregido para bases nuevas), se copian las filas y se renombra.
`legacy_alter_table=ON` evita que SQLite reescriba vistas rotas de la base
real al renombrar (trampa documentada en la 291).
"""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger("spj.migrations.308")

_COLUMNAS = (
    "id, shift_id, z_cut_id, branch_id, expected_amount, counted_amount, amount, detected_by,"
    " operation_id, responsible_user_id, classification, severity, tolerance_amount,"
    " recurrence_count, status, explanation, explained_by, reviewed_by, resolution, resolved_by"
)


def _ddl_fuente() -> str:
    schema = importlib.import_module(
        "migrations.standalone.175_cash_register_bounded_context_schema")
    for sentencia in schema.DDL:
        if "CREATE TABLE IF NOT EXISTS cash_differences (" in sentencia:
            return sentencia
    raise RuntimeError("308: la 175 ya no declara cash_differences")


def run(conn) -> None:
    fila = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='cash_differences'"
    ).fetchone()
    if fila is None or "reviewed_by<>responsible_user_id" in str(fila[0]):
        logger.info("308: cash_differences ya aplica la regla de dos personas.")
        return
    indices = [
        str(r[0]) for r in conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name='cash_differences'"
            " AND sql IS NOT NULL")
    ]
    nuevo = _ddl_fuente().replace(
        "CREATE TABLE IF NOT EXISTS cash_differences (", "CREATE TABLE cash_differences_308 (")
    conn.commit()
    conn.execute("PRAGMA legacy_alter_table=ON")
    try:
        conn.execute("BEGIN")
        conn.execute(nuevo)
        conn.execute(f"INSERT INTO cash_differences_308 ({_COLUMNAS}) "
                     f"SELECT {_COLUMNAS} FROM cash_differences")
        conn.execute("DROP TABLE cash_differences")
        conn.execute("ALTER TABLE cash_differences_308 RENAME TO cash_differences")
        for sql in indices:
            conn.execute(sql)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA legacy_alter_table=OFF")
    logger.info("308: cash_differences reconstruida con la regla de dos personas.")


up = run
