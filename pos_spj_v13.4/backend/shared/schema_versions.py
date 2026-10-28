"""Station database schema version — ONE rule for every consumer.

A station's database schema version is the highest NUMERIC migration
identifier of the SQLite lane (`migrations/engine.py::MIGRATIONS`, ids such as
"000", "016", "353"). The PostgreSQL lane (`PG_MIGRATIONS`, ids "p001",
"p002", …) migrates the CENTRAL database, never a station, so its identifiers
do not count and must never break the computation.

Used by:
* `migrations/engine.py::target_schema_version()` — what a build migrates to
  (release manifest `database_schema.migrates_to`, `release.json`);
* `backend/infrastructure/db/sqlite_backup.py::database_schema_version()` —
  what a station's database IS (self-test, backups, relocation, eligibility).

Both sides must agree, or the updater would compare different scales.
"""
from __future__ import annotations

from typing import Iterable


def is_station_migration_id(identifier: object) -> bool:
    """True for the SQLite lane's ids: ASCII digits only ("000", "353")."""
    text = str(identifier).strip() if identifier is not None else ""
    return bool(text) and text.isascii() and text.isdigit()


def station_schema_version(identifiers: Iterable[object]) -> int | None:
    """Highest station (numeric) migration id, or None when there is none.

    Non-numeric ids (the PostgreSQL lane, or anything unexpected) are ignored
    instead of raising: `int("p001")` is exactly the error this replaces.
    """
    numeric = [int(str(identifier).strip()) for identifier in identifiers
               if is_station_migration_id(identifier)]
    return max(numeric) if numeric else None
