"""Apoyo de las pruebas de SDLC-ARQ-TERM-002 (re-anclar la estación).

Base: el esquema born-clean real (`make_db()`) más las migraciones que el ítem
necesita, construida una vez por módulo; cada prueba trabaja sobre una copia en
memoria. Nunca se abre un `.db` real.
"""
from __future__ import annotations

import importlib
import sqlite3
from types import SimpleNamespace

from backend.infrastructure.db.repositories.settings.installation_branch_repository import (
    INSTALLATION_BRANCH_KEY,
)
from backend.shared.ids import new_uuid

#: Motor de replicación (pendientes de sincronizar) y el sembrado del permiso.
MIGRACIONES = ("350_replication_engine", "357_seed_installation_reanchor_permission",
               "392_terminal_identity")


def build_template() -> sqlite3.Connection:
    from tests.integration._born_clean_db import make_db

    conn = make_db()
    for nombre in MIGRACIONES:
        importlib.import_module(f"migrations.standalone.{nombre}").run(conn)
    conn.commit()
    return conn


def copy_of(template: sqlite3.Connection) -> sqlite3.Connection:
    copia = sqlite3.connect(":memory:")
    template.backup(copia)
    copia.row_factory = sqlite3.Row
    copia.execute("PRAGMA foreign_keys=ON")   # como la aplicación
    return copia


def sucursal(conn, nombre: str, *, activa: int = 1) -> str:
    bid = new_uuid()
    conn.execute("INSERT INTO sucursales (id, nombre, activa) VALUES (?,?,?)",
                 (bid, nombre, activa))
    conn.commit()
    return bid


def ancla(conn) -> str | None:
    fila = conn.execute("SELECT valor FROM configuraciones WHERE clave=?",
                        (INSTALLATION_BRANCH_KEY,)).fetchone()
    return str(fila[0]) if fila else None


def quitar_ancla(conn) -> None:
    conn.execute("DELETE FROM configuraciones WHERE clave=?", (INSTALLATION_BRANCH_KEY,))
    conn.commit()


def usuario(conn, rol: str, sucursal_id: str | None) -> str:
    uid = new_uuid()
    conn.execute("INSERT INTO usuarios (id, nombre, usuario, password_hash, rol, sucursal_id,"
                 " activo) VALUES (?,?,?,?,?,?,1)",
                 (uid, rol, f"{rol}-{uid[-6:]}", "x", rol, sucursal_id))
    conn.commit()
    return uid


def login(user_id: str, rol: str, sucursal_id: str | None):
    """Lo que `ApplicationContextBuilder.build()` lee de un login correcto."""
    return SimpleNamespace(
        credentials=SimpleNamespace(id=user_id, branch_id=sucursal_id, role=rol,
                                    full_name=rol, username=rol),
        session=SimpleNamespace(workstation_id="ws-term-002", session_id=new_uuid()),
    )


def _sin_llaves(conn, sql: str, args: tuple) -> None:
    """Siembra filas sin construir toda la cadena de caja/estación."""
    conn.execute("PRAGMA foreign_keys=OFF")
    try:
        conn.execute(sql, args)
        conn.commit()
    finally:
        conn.execute("PRAGMA foreign_keys=ON")


def turno(conn, branch_id: str, status: str = "OPEN") -> str:
    sid = new_uuid()
    cerrado = status == "CLOSED"
    _sin_llaves(
        conn,
        "INSERT INTO cash_shifts (id, branch_id, register_id, drawer_id, terminal_id,"
        " cashier_user_id, opening_amount, opening_operation_id, status, opened_at,"
        " z_cut_id, closed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, branch_id, new_uuid(), new_uuid(), new_uuid(), new_uuid(), "0", new_uuid(),
         status, "2026-11-02T08:00:00", new_uuid() if cerrado else None,
         "2026-11-02T20:00:00" if cerrado else None),
    )
    return sid


def estacion(conn, branch_id: str) -> str:
    station = new_uuid()
    conn.execute("INSERT INTO replication_stations (id, branch_id, created_at, updated_at)"
                 " VALUES (?,?,?,?)", (station, branch_id, "2026-11-02", "2026-11-02"))
    conn.commit()
    return station


def sobre(conn, station_id: str, state: str, *, seq: int = 1) -> str:
    eid = new_uuid()
    _sin_llaves(
        conn,
        "INSERT INTO replication_envelopes (id, station_id, source, source_row_id, event_id,"
        " event_type, operation_id, sequence_no, aggregate_type, aggregate_id,"
        " aggregate_version, envelope_json, content_hash, state, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (eid, station_id, "cash_register", new_uuid(), new_uuid(), "CASH_TEST", new_uuid(),
         seq, "cash", new_uuid(), 1, "{}", "h", state, "2026-11-02"),
    )
    return eid


def hecho_en_outbox(conn) -> str:
    """Un hecho de Caja que el motor aún no preparó (sin sobre)."""
    oid = new_uuid()
    _sin_llaves(
        conn,
        "INSERT INTO cash_outbox (id, event_id, event_name, operation_id, entity_id,"
        " payload_json, created_at) VALUES (?,?,?,?,?,?,?)",
        (oid, new_uuid(), "CASH_SHIFT_OPENED", new_uuid(), new_uuid(), "{}", "2026-11-02"),
    )
    return oid


def vincular_central(conn, branch_id: str, status: str = "ENROLLED") -> None:
    importlib.import_module("migrations.standalone.354_device_enrollment").run(conn)
    conn.execute("INSERT INTO device_enrollment (station_id, central_url, branch_id,"
                 " workstation_type, public_key, status, enrolled_at)"
                 " VALUES (?,?,?,?,?,?,?)",
                 (new_uuid(), "https://central.example", branch_id, "POS", "pk", status,
                  "2026-11-02"))
    conn.commit()


def auditoria(conn) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT accion, modulo, entidad, entidad_id, usuario, sucursal_id, valor_antes,"
        " valor_despues, detalles FROM audit_logs WHERE accion='instalacion.reanclar'"
        " ORDER BY rowid")]
