"""CI helper: prove that repair/upgrade/uninstall keep the station's data.

    python ci_data_marker.py write <database>   → adds the marker rows
    python ci_data_marker.py check <database>   → exit 0 only if all of them are there

What must survive (requisitos-arquitectura §13): sync queue, terminal identity,
branch anchor and permissions, each in its REAL table. The rows carry ids nothing
looks up, so they do not change how the application behaves. The branch anchor is
never written, because it decides what the station is: `write` records the value
it finds and `check` compares it. Same for how many permission rows exist.

Uses the runner's Python only to INSPECT the database file; the installed
application itself runs without Python on PATH.
"""
from __future__ import annotations

import sqlite3
import sys

_ID = "ci-marker"
_NOW = "2026-01-01T00:00:00+00:00"

#: (what it proves, query that must return a row)
_PRESENT = (
    ("marcador", "SELECT 1 FROM ci_marker WHERE v = 'keep'"),
    ("cola de sincronización",
     f"SELECT 1 FROM replication_envelopes WHERE id = '{_ID}' AND state = 'PENDING'"),
    ("estación de sincronización", f"SELECT 1 FROM replication_stations WHERE id = '{_ID}'"),
    ("identidad de terminal",
     f"SELECT 1 FROM software_station_settings WHERE workstation_key = '{_ID}'"),
    ("permisos", f"SELECT 1 FROM rol_permisos WHERE id = '{_ID}'"),
)
_ANCHOR = ("SELECT COALESCE(MAX(valor), '') FROM configuraciones "
           "WHERE clave = 'sucursal_instalacion_id'")
_PERMISSION_COUNT = "SELECT COUNT(*) FROM rol_permisos"


def _write(connection: sqlite3.Connection) -> None:
    connection.execute("CREATE TABLE IF NOT EXISTS ci_marker (v TEXT)")
    connection.execute("INSERT INTO ci_marker VALUES ('keep')")
    connection.execute(
        "INSERT OR IGNORE INTO replication_stations (id, branch_id, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)", (_ID, _ID, _NOW, _NOW))
    connection.execute(
        "INSERT OR IGNORE INTO replication_envelopes (id, station_id, source, source_row_id, "
        "event_id, event_type, operation_id, sequence_no, aggregate_type, aggregate_id, "
        "aggregate_version, envelope_json, content_hash, state, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 1, '{}', ?, 'PENDING', ?)",
        (_ID, _ID, _ID, _ID, _ID, _ID, _ID, _ID, _ID, _ID, _NOW))
    connection.execute(
        "INSERT OR IGNORE INTO software_station_settings (id, workstation_key) VALUES (?, ?)",
        (_ID, _ID))
    connection.execute(
        "INSERT OR IGNORE INTO rol_permisos (id, rol_id, modulo, accion) VALUES (?, ?, ?, ?)",
        (_ID, _ID, _ID, _ID))
    connection.execute("DELETE FROM ci_marker WHERE v <> 'keep'")
    connection.execute(f"INSERT INTO ci_marker SELECT 'anchor:' || ({_ANCHOR})")
    connection.execute(f"INSERT INTO ci_marker SELECT 'permissions:' || ({_PERMISSION_COUNT})")
    connection.commit()


def _missing(connection: sqlite3.Connection) -> list[str]:
    missing = [name for name, query in _PRESENT if connection.execute(query).fetchone() is None]
    recorded = dict(row[0].split(":", 1) for row in connection.execute(
        "SELECT v FROM ci_marker WHERE v <> 'keep'"))
    if connection.execute(_ANCHOR).fetchone()[0] != recorded.get("anchor"):
        missing.append("ancla de sucursal")
    if connection.execute(_PERMISSION_COUNT).fetchone()[0] < int(recorded.get("permissions", 0)):
        missing.append("permisos (se perdieron filas)")
    return missing


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2 or argv[0] not in {"write", "check"}:
        print(__doc__)
        return 2
    command, database = argv
    connection = sqlite3.connect(database)
    try:
        if command == "write":
            _write(connection)
            print("marker escrito")
            return 0
        missing = _missing(connection)
    except sqlite3.Error as exc:
        print(f"ERROR: {exc}")
        return 1
    finally:
        connection.close()
    print("marker presente" if not missing else "marker AUSENTE: " + ", ".join(missing))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
