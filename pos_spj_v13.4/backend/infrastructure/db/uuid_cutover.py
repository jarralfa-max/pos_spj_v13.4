"""Atomic UUIDv7 identity cutover engine (FASE 2.5 / migración 200).

Converts integer PK/FK tables to UUIDv7 TEXT keys in a single transaction,
following REGLA CERO's 14-step procedure. This is the reusable machinery — it is
fed an explicit table/FK specification (legacy tables declare FKs by convention,
not constraints, so the relationships must be configured) and rewrites every PK
and FK in place using temporary ``old_id -> uuid`` maps.

Design notes
------------
* All ``old_id -> uuid`` maps are built up-front for every table, so FK rewrites
  (including self-referential ones) always resolve from an already-complete map —
  no topological ordering of the data rewrite is required.
* The new tables are created by introspecting ``PRAGMA table_info`` so any column
  layout is supported; the PK column becomes ``TEXT PRIMARY KEY`` and FK columns
  become ``TEXT``.
* Orphan FKs (a value with no parent row) abort the cutover by default — a partial
  identity migration is never allowed (REGLA CERO). They can be nulled instead via
  ``on_orphan="null"``.
* Everything runs inside one transaction; any error rolls the whole thing back.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any, Callable

from backend.shared.ids import new_uuid


@dataclass(frozen=True)
class TableSpec:
    name: str
    # Single integer PK column to convert to UUID, or None for junction/config
    # tables (composite PK or PK='clave'/'key') that have no own integer identity
    # but whose FK columns still must be rewritten to point at UUID parents.
    pk: str | None = "id"
    # functional FK column -> parent table whose PK it references
    fks: dict[str, str] = field(default_factory=dict)


class UuidCutoverError(RuntimeError):
    pass


class IntegerIdentityError(RuntimeError):
    """Raised at startup when the DB still has INTEGER PK identity (un-cut)."""


# Infra tables that legitimately keep an integer id (not domain entities).
_NON_DOMAIN_PREFIXES = ("sqlite_", "schema_")


def find_integer_pks(conn: sqlite3.Connection) -> dict[str, list[str]]:
    """Return {table: [cols]} for every remaining INTEGER PRIMARY KEY column.

    Excludes SQLite/migration infra tables. After the UUIDv7 cut (migración 200)
    this must be empty — a non-empty result means the DB is un-cut."""
    out: dict[str, list[str]] = {}
    for (table,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall():
        if any(table.startswith(p) for p in _NON_DOMAIN_PREFIXES):
            continue
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall():
            col_name, col_type, pk = row[1], (row[2] or ""), row[5]
            if pk and col_type.upper() in ("INTEGER", "INT"):
                out.setdefault(table, []).append(col_name)
    return out


def assert_uuid_identity(conn: sqlite3.Connection) -> None:
    """REGLA CERO paso 13: block app start if any INTEGER PK remains.

    The runtime assumes the post-cut TEXT/UUIDv7 schema (e.g. abrir_turno,
    crear_lote mint UUIDs into id columns). Starting against an un-cut DB would
    fail later with a cryptic 'datatype mismatch'; fail fast with the runbook."""
    bad = find_integer_pks(conn)
    if not bad:
        return
    sample = ", ".join(f"{t}.{cols[0]}" for t, cols in list(bad.items())[:8])
    raise IntegerIdentityError(
        f"La DB no nació UUIDv7 limpia: quedan {len(bad)} tablas con PRIMARY KEY "
        f"entera (p.ej. {sample}). El schema fuente (migrations/) es born-clean; "
        f"esta base fue creada por código viejo o quedó contaminada.\n"
        f"Plan B (desarrollo — flujo normal):\n"
        f"  1) NO ejecutes la migración 200 como solución normal.\n"
        f"  2) Corrige el schema fuente que generó estas tablas (migrations/ y "
        f"cualquier DDL fuera de migrations) si el bootstrap volvió a crearlas.\n"
        f"  3) Resetea la BD de desarrollo: docs/runbooks/dev_db_reset.md "
        f"(respaldo opcional, borrar el .db y arrancar; nace limpia).\n"
        f"Excepción (producción, conservación de datos): sólo en ese caso usa el "
        f"corte UUID atómico (SPJ_UUID_CUTOVER_CONFIRMED=1 + migración 200; "
        f"foreign_key_check + rollback ante cualquier fallo)."
    )


class UuidCutover:
    def __init__(
        self,
        connection: sqlite3.Connection,
        specs: list[TableSpec],
        *,
        id_factory: Callable[[], str] = new_uuid,
        on_orphan: str = "abort",
    ) -> None:
        if on_orphan not in ("abort", "null"):
            raise ValueError("on_orphan must be 'abort' or 'null'")
        self._conn = connection
        self._specs = {s.name: s for s in specs}
        self._id = id_factory
        self._on_orphan = on_orphan
        self._maps: dict[str, dict[Any, str]] = {}

    # ── public API ──────────────────────────────────────────────────────────────
    def report_orphans(self) -> dict[str, list[tuple]]:
        """Dry-run: list FK values with no matching parent row, per table.column.

        Pre-flight check before a cut — never mutates. Empty dict means every
        functional FK resolves to a real parent."""
        report: dict[str, list[tuple]] = {}
        for spec in self._specs.values():
            for col, parent in spec.fks.items():
                rows = self._conn.execute(
                    f'SELECT child."{spec.pk or "rowid"}", child."{col}" '
                    f'FROM "{spec.name}" child '
                    f'LEFT JOIN "{parent}" p ON p."id" = child."{col}" '
                    f'WHERE child."{col}" IS NOT NULL AND p."id" IS NULL '
                    f"AND child.\"{col}\" NOT IN (0, '0', '', '0.0')"
                ).fetchall()
                if rows:
                    report[f"{spec.name}.{col}->{parent}"] = [tuple(r) for r in rows]
        return report

    def run(self) -> dict[str, int]:
        """Execute the atomic cutover. Returns row counts per table.

        Raises UuidCutoverError (and leaves the DB untouched) on any failure."""
        counts: dict[str, int] = {}
        try:
            self._conn.execute("PRAGMA foreign_keys = OFF")
            self._conn.execute("BEGIN")
            # Capture explicit indexes / triggers / views before they are torn down
            # with their tables; views are dropped up front because SQLite
            # re-validates every view on each ALTER TABLE RENAME (a single stale
            # view would otherwise abort the whole cut).
            indexes, triggers, views = self._capture_schema_objects()
            # SQLite re-validates every view AND trigger on each ALTER TABLE
            # RENAME, so a single stale one (referencing a dropped/missing object)
            # would abort the cut. Drop them all up front; recreate after.
            for tname, _ in triggers:
                self._conn.execute(f'DROP TRIGGER IF EXISTS "{tname}"')
            for vname, _ in views:
                self._conn.execute(f'DROP VIEW IF EXISTS "{vname}"')
            self._build_id_maps()
            for name in self._specs:
                counts[name] = self._rewrite_table(name)
            self._validate_counts(counts)
            for name in self._specs:
                self._conn.execute(f'DROP TABLE "{name}"')
                self._conn.execute(f'ALTER TABLE "{name}__uuid_new" RENAME TO "{name}"')
            self._restore_schema_objects(indexes, triggers, views)
            self._foreign_key_check()
            self._conn.execute("COMMIT")
        except Exception as exc:  # noqa: BLE001 — atomicity: roll back everything
            try:
                self._conn.execute("ROLLBACK")
            except Exception:
                pass
            if isinstance(exc, UuidCutoverError):
                raise
            raise UuidCutoverError(str(exc)) from exc
        finally:
            self._maps.clear()
        return counts

    # ── internals ───────────────────────────────────────────────────────────────
    @staticmethod
    def _default_sql(dflt: Any) -> str:
        """Re-emit a column default safely.

        ``PRAGMA table_info`` returns expression defaults (e.g. a parenthesised
        ``(datetime('now'))``) stripped of their wrapping parens, so a naive
        re-emit produces ``DEFAULT datetime('now')`` which is a syntax error.
        Function-call / expression defaults must be wrapped in parens again;
        plain literals (numbers, 'strings', NULL, CURRENT_TIMESTAMP) are kept
        verbatim."""
        d = str(dflt)
        if "(" in d and not d.lstrip().startswith("("):
            return f"({d})"
        return d

    def _columns(self, table: str) -> list[tuple]:
        return self._conn.execute(f'PRAGMA table_info("{table}")').fetchall()

    def _capture_schema_objects(self):
        """Snapshot explicit indexes/triggers (on cut tables) and all views.

        Auto-indexes (UNIQUE/PK, ``sql IS NULL``) cannot be replayed as DDL and
        are not captured — explicit ``CREATE [UNIQUE] INDEX`` are. Indexes and
        triggers are dropped automatically when their table is dropped, so we
        recreate them from the saved DDL after the rename."""
        names = set(self._specs)
        indexes = [
            (r[0], r[1]) for r in self._conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='index' "
                "AND sql IS NOT NULL"
            ).fetchall() if r[1] and self._obj_table(r[1]) in names
        ]
        # Triggers and views are captured wholesale (not filtered to cut tables):
        # any stale one blocks the rename, so all are dropped and recreated.
        triggers = [
            (r[0], r[1]) for r in self._conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger' AND sql IS NOT NULL"
            ).fetchall()
        ]
        views = [
            (r[0], r[1]) for r in self._conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='view' AND sql IS NOT NULL"
            ).fetchall()
        ]
        return indexes, triggers, views

    def _obj_table(self, sql: str) -> str:
        """Best-effort table name for an index DDL (the token after ON)."""
        low = sql.lower()
        i = low.rfind(" on ")
        if i < 0:
            return ""
        rest = sql[i + 4:].strip()
        tbl = rest.split("(")[0].strip().strip('"').strip("`").strip("[").strip("]")
        return tbl

    def _restore_schema_objects(self, indexes, triggers, views) -> None:
        """Recreate captured indexes/triggers/views after the rename.

        Indexes on the rewritten tables always recreate. A trigger or view that
        was already broken (references a missing table/column) cannot be
        recreated and is skipped — it was unusable before the cut too."""
        for _name, sql in indexes:
            self._conn.execute(sql)
        for _name, sql in triggers + views:
            try:
                self._conn.execute(sql)
            except Exception:  # noqa: BLE001 — a pre-broken object stays dropped
                pass

    def _build_id_maps(self) -> None:
        # Maps are keyed by str(old_pk) so that a FK stored as TEXT '1' resolves
        # to an INTEGER parent PK 1 (forward-compatible str identity columns mean
        # child FK and parent PK can differ in storage type pre-cut).
        for spec in self._specs.values():
            if spec.pk is None:
                continue  # junction/config table — no own identity to remap
            rows = self._conn.execute(f'SELECT "{spec.pk}" FROM "{spec.name}"').fetchall()
            self._maps[spec.name] = {str(r[0]): self._id() for r in rows}

    def _new_pk(self, table: str, old: Any) -> str:
        return self._maps[table][str(old)]

    # Legacy "no reference" sentinels. An INTEGER PRIMARY KEY (AUTOINCREMENT)
    # never produces 0 or an empty string, so a FK holding one of these can never
    # resolve to a real parent — it means "none" and becomes NULL (not an orphan).
    _NULL_SENTINELS = (0, "0", "", "0.0")

    def _new_fk(self, parent: str, old: Any, *, column: str, table: str) -> Any:
        if old is None or old in self._NULL_SENTINELS:
            return None
        mapped = self._maps.get(parent, {}).get(str(old))
        if mapped is not None:
            return mapped
        # orphan: value points to a non-existent parent row
        if self._on_orphan == "null":
            return None
        raise UuidCutoverError(
            f"orphan FK {table}.{column}={old!r} has no parent in {parent}"
        )

    def _rewrite_table(self, name: str) -> int:
        spec = self._specs[name]
        cols = self._columns(name)
        col_names = [c[1] for c in cols]
        if spec.pk is not None and spec.pk not in col_names:
            raise UuidCutoverError(f"{name}: pk column '{spec.pk}' not found")

        # Existing PK columns (for junction/config tables we preserve them as a
        # table-level PRIMARY KEY since FK columns may become TEXT).
        existing_pk = [c[1] for c in sorted(cols, key=lambda c: c[5]) if c[5]]

        # Build the new CREATE TABLE with TEXT id + TEXT fks.
        defs = []
        for _cid, cname, ctype, notnull, dflt, _pk in cols:
            if spec.pk is not None and cname == spec.pk:
                defs.append(f'"{cname}" TEXT PRIMARY KEY')
                continue
            col_type = "TEXT" if cname in spec.fks else (ctype or "")
            piece = f'"{cname}" {col_type}'.rstrip()
            if notnull:
                piece += " NOT NULL"
            if dflt is not None:
                piece += f" DEFAULT {self._default_sql(dflt)}"
            defs.append(piece)
        # Preserve composite/non-id PK for pk=None tables.
        if spec.pk is None and existing_pk:
            cols_sql = ", ".join(f'"{c}"' for c in existing_pk)
            defs.append(f"PRIMARY KEY ({cols_sql})")
        self._conn.execute(f'CREATE TABLE "{name}__uuid_new" ({", ".join(defs)})')

        # Copy + rewrite every row.
        placeholders = ", ".join("?" * len(col_names))
        quoted = ", ".join(f'"{c}"' for c in col_names)
        insert = f'INSERT INTO "{name}__uuid_new" ({quoted}) VALUES ({placeholders})'
        n = 0
        for row in self._conn.execute(f'SELECT {quoted} FROM "{name}"').fetchall():
            values = list(row)
            for i, cname in enumerate(col_names):
                if cname == spec.pk:
                    values[i] = self._new_pk(name, row[i])
                elif cname in spec.fks:
                    values[i] = self._new_fk(
                        spec.fks[cname], row[i], column=cname, table=name
                    )
            self._conn.execute(insert, values)
            n += 1
        return n

    def _validate_counts(self, counts: dict[str, int]) -> None:
        for name, copied in counts.items():
            original = self._conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            if original != copied:
                raise UuidCutoverError(
                    f"{name}: row count mismatch original={original} copied={copied}"
                )

    def _foreign_key_check(self) -> None:
        self._conn.execute("PRAGMA foreign_keys = ON")
        problems = self._conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise UuidCutoverError(f"foreign_key_check failed: {problems}")
