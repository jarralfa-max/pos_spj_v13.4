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
                    f'WHERE child."{col}" IS NOT NULL AND p."id" IS NULL'
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
            self._build_id_maps()
            for name in self._specs:
                counts[name] = self._rewrite_table(name)
            self._validate_counts(counts)
            for name in self._specs:
                self._conn.execute(f'DROP TABLE "{name}"')
                self._conn.execute(f'ALTER TABLE "{name}__uuid_new" RENAME TO "{name}"')
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
    def _columns(self, table: str) -> list[tuple]:
        return self._conn.execute(f'PRAGMA table_info("{table}")').fetchall()

    def _build_id_maps(self) -> None:
        for spec in self._specs.values():
            if spec.pk is None:
                continue  # junction/config table — no own identity to remap
            rows = self._conn.execute(f'SELECT "{spec.pk}" FROM "{spec.name}"').fetchall()
            self._maps[spec.name] = {r[0]: self._id() for r in rows}

    def _new_pk(self, table: str, old: Any) -> str:
        return self._maps[table][old]

    def _new_fk(self, parent: str, old: Any, *, column: str, table: str) -> Any:
        if old is None:
            return None
        mapped = self._maps.get(parent, {}).get(old)
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
                piece += f" DEFAULT {dflt}"
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
