#!/usr/bin/env python3
"""born_clean_audit.py — Diagnóstico Plan B born-clean UUIDv7.

Crea una DB temporal, ejecuta el bootstrap normal (m000 + engine) y produce el
mapa de deuda de identidad entera del schema ACTIVO:

  * total de tablas;
  * tablas con id TEXT PRIMARY KEY (born-clean);
  * tablas con PK entera (find_integer_pks — criterio canónico del guard);
  * tablas con PK natural/compuesta;
  * tablas sin PK;
  * tablas con AUTOINCREMENT;
  * columnas FK funcionales INTEGER;
  * columnas FK funcionales con DEFAULT 1;
  * archivo/migración responsable de crear cada tabla legacy.

Uso:
    python tools/born_clean_audit.py            # imprime resumen
    python tools/born_clean_audit.py --md FILE  # además escribe el reporte md
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PKG))

FUNCTIONAL_FK_RE = re.compile(
    r"^(?:.*_id|sucursal|branch|producto|product|cliente|customer|venta|sale|"
    r"usuario|user|proveedor|supplier|empleado|personal|turno|caja|batch|lote|order)$",
    re.I,
)
# Columnas *_id que NO son identidad de dominio (versiones/contadores/técnicas).
NON_IDENTITY_ID_COLS = {
    "device_version", "event_version",
}


def bootstrap(conn: sqlite3.Connection) -> None:
    import migrations.m000_base_schema as base
    from migrations import engine as migrator

    base.up(conn)
    conn.commit()
    migrator.up(conn)
    conn.commit()


def is_functional_fk(col: str) -> bool:
    c = col.lower()
    if c == "id" or c in NON_IDENTITY_ID_COLS:
        return False
    return bool(FUNCTIONAL_FK_RE.match(c)) and c.endswith("_id")


def audit(conn: sqlite3.Connection) -> dict:
    from backend.infrastructure.db.uuid_cutover import find_integer_pks

    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()]
    int_pks = find_integer_pks(conn)

    text_pk, natural_pk, no_pk = [], [], []
    autoinc, int_fks, default1 = [], defaultdict(list), defaultdict(list)

    for t in tables:
        info = conn.execute(f'PRAGMA table_info("{t}")').fetchall()
        pk_cols = [r for r in info if r[5]]
        if not pk_cols:
            no_pk.append(t)
        elif len(pk_cols) == 1 and (pk_cols[0][2] or "").upper() == "TEXT" and pk_cols[0][1] == "id":
            text_pk.append(t)
        elif t not in int_pks:
            natural_pk.append(t)

        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()
        if sql_row and sql_row[0] and "AUTOINCREMENT" in sql_row[0].upper():
            autoinc.append(t)

        for r in info:
            col, ctype, dflt = r[1], (r[2] or "").upper(), r[4]
            if is_functional_fk(col):
                if ctype in ("INTEGER", "INT"):
                    int_fks[t].append(col)
                if dflt is not None and str(dflt).strip("()\"' ") == "1":
                    default1[t].append(col)

    return {
        "tables": tables,
        "int_pks": int_pks,
        "text_pk": text_pk,
        "natural_pk": natural_pk,
        "no_pk": no_pk,
        "autoinc": autoinc,
        "int_fks": dict(int_fks),
        "default1": dict(default1),
    }


def attribute_creators(table_names: list[str]) -> dict[str, list[str]]:
    """Mapa tabla -> archivos de migrations/ que la crean (CREATE TABLE)."""
    creators: dict[str, list[str]] = defaultdict(list)
    files = sorted((PKG / "migrations").rglob("*.py"))
    rx_cache = {
        t: re.compile(rf"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\"'`\[]?{re.escape(t)}[\"'`\]]?\s*\(", re.I)
        for t in table_names
    }
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        rel = str(f.relative_to(PKG))
        for t, rx in rx_cache.items():
            if rx.search(text):
                creators[t].append(rel)
    return dict(creators)


def render_md(a: dict, creators: dict[str, list[str]]) -> str:
    lines = [
        "# Auditoría born-clean UUIDv7 — schema activo (FASE 0)",
        "",
        "Generado por `tools/born_clean_audit.py` sobre una DB temporal con el",
        "bootstrap normal (`m000_base_schema.up` + `migrations.engine.up`).",
        "",
        "## Censo",
        "",
        f"| Métrica | Valor |",
        f"|---|---|",
        f"| Tablas totales | {len(a['tables'])} |",
        f"| `id TEXT PRIMARY KEY` (born-clean) | {len(a['text_pk'])} |",
        f"| PK entera (`find_integer_pks`) | **{len(a['int_pks'])}** |",
        f"| PK natural/compuesta | {len(a['natural_pk'])} |",
        f"| Sin PK | {len(a['no_pk'])} |",
        f"| Con AUTOINCREMENT | {len(a['autoinc'])} |",
        f"| Tablas con FK funcional INTEGER | {len(a['int_fks'])} |",
        f"| Tablas con `DEFAULT 1` en FK funcional | {len(a['default1'])} |",
        "",
        "## Tablas legacy restantes (PK entera) y archivo creador",
        "",
        "| Tabla | PK | Creador(es) |",
        "|---|---|---|",
    ]
    for t in sorted(a["int_pks"]):
        c = "; ".join(creators.get(t, ["(no encontrado en migrations/)"]))
        lines.append(f"| {t} | {', '.join(a['int_pks'][t])} | {c} |")

    lines += ["", "## AUTOINCREMENT", ""]
    lines += [f"- {t}" for t in sorted(a["autoinc"])] or ["- (ninguna)"]

    lines += ["", "## FK funcionales INTEGER", ""]
    for t in sorted(a["int_fks"]):
        lines.append(f"- {t}: {', '.join(a['int_fks'][t])}")

    lines += ["", "## DEFAULT 1 en FK funcional", ""]
    for t in sorted(a["default1"]):
        lines.append(f"- {t}: {', '.join(a['default1'][t])}")

    lines += ["", "## Sin PK", ""]
    lines += [f"- {t}" for t in sorted(a["no_pk"])] or ["- (ninguna)"]
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", help="ruta del reporte markdown a escribir")
    args = ap.parse_args()

    conn = sqlite3.connect(":memory:")
    bootstrap(conn)
    a = audit(conn)
    creators = attribute_creators(sorted(a["int_pks"]))

    print(f"tablas={len(a['tables'])} text_pk={len(a['text_pk'])} "
          f"int_pk={len(a['int_pks'])} natural={len(a['natural_pk'])} "
          f"no_pk={len(a['no_pk'])} autoinc={len(a['autoinc'])} "
          f"fk_int={len(a['int_fks'])} default1={len(a['default1'])}")

    if args.md:
        Path(args.md).write_text(render_md(a, creators), encoding="utf-8")
        print(f"reporte -> {args.md}")

    return 0 if not a["int_pks"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
