#!/usr/bin/env python3
# tools/fix_invalid_branch_identity.py — SPJ POS v13.4
"""
Reparación controlada de identidad de sucursales en una DB de desarrollo.

Corrige dos contaminaciones detectadas en campo:
  1. Filas de `sucursales` con id NULL, '', 'None' o 'null'
     (creadas por código pre-born-clean sobre esquema dual).
  2. La clave `configuraciones.sucursal_instalacion_id` guardada como
     'None'/''/'null' o apuntando a una sucursal inexistente/inactiva.

Uso:
    python tools/fix_invalid_branch_identity.py --db ruta/pos_spj.db --dry-run
    python tools/fix_invalid_branch_identity.py --db ruta/pos_spj.db --apply
    python tools/fix_invalid_branch_identity.py --db ruta/pos_spj.db --apply \
        --prefer-name "Cadenas"

  --dry-run       Solo reporta; no escribe nada (default si no se pasa --apply).
  --apply         Aplica la reparación dentro de una transacción.
  --prefer-name   Tras reparar, fija la sucursal de instalación a la sucursal
                  activa con ese nombre exacto.

Solo para fase de desarrollo: no conserva data legacy ni crea mapas de
compatibilidad. Cada sucursal inválida recibe un UUIDv7 nuevo vía
backend.shared.ids.new_uuid().
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from backend.shared.ids import new_uuid  # noqa: E402

INSTALLATION_BRANCH_KEY = "sucursal_instalacion_id"

INVALID_ID_SQL = (
    "id IS NULL OR TRIM(id) = '' OR LOWER(TRIM(id)) IN ('none','null')"
)
VALID_ID_SQL = (
    "id IS NOT NULL AND TRIM(id) != '' "
    "AND LOWER(TRIM(id)) NOT IN ('none','null')"
)


def _is_invalid_identity(value) -> bool:
    return value is None or str(value).strip().lower() in ("", "none", "null")


def _snapshot(conn: sqlite3.Connection) -> dict:
    branches = conn.execute(
        "SELECT rowid, id, nombre, COALESCE(activa,1) FROM sucursales ORDER BY rowid"
    ).fetchall()
    row = conn.execute(
        "SELECT valor FROM configuraciones WHERE clave=?",
        (INSTALLATION_BRANCH_KEY,),
    ).fetchone()
    return {
        "branches": branches,
        "install_key_present": row is not None,
        "install_key_value": row[0] if row else None,
    }


def _print_snapshot(title: str, snap: dict) -> None:
    print(f"\n== {title} ==")
    print("sucursales (rowid | id | nombre | activa):")
    for rowid, bid, nombre, activa in snap["branches"]:
        marker = "  <-- INVÁLIDA" if _is_invalid_identity(bid) else ""
        print(f"  {rowid} | {bid!r} | {nombre} | {activa}{marker}")
    if snap["install_key_present"]:
        val = snap["install_key_value"]
        marker = "  <-- INVÁLIDA" if _is_invalid_identity(val) else ""
        print(f"{INSTALLATION_BRANCH_KEY} = {val!r}{marker}")
    else:
        print(f"{INSTALLATION_BRANCH_KEY} = (clave ausente)")


def _resolve_install_key(conn: sqlite3.Connection) -> tuple[str, str] | None:
    """Devuelve (id, nombre) de la sucursal a la que resuelve la clave, o None."""
    row = conn.execute(
        "SELECT s.id, s.nombre FROM sucursales s "
        "JOIN configuraciones c ON c.clave=? AND s.id = c.valor "
        "WHERE COALESCE(s.activa,1)=1 AND s.id IS NOT NULL "
        "AND TRIM(s.id) != '' AND LOWER(TRIM(s.id)) NOT IN ('none','null')",
        (INSTALLATION_BRANCH_KEY,),
    ).fetchone()
    return (str(row[0]), str(row[1])) if row else None


def repair(db_path: str, apply: bool, prefer_name: str | None) -> int:
    if not os.path.exists(db_path):
        print(f"ERROR: no existe la base de datos: {db_path}")
        return 2

    conn = sqlite3.connect(db_path)
    try:
        before = _snapshot(conn)
        _print_snapshot("ANTES", before)

        invalid_branches = conn.execute(
            f"SELECT rowid, nombre FROM sucursales WHERE {INVALID_ID_SQL}"
        ).fetchall()
        key_invalid = before["install_key_present"] and (
            _is_invalid_identity(before["install_key_value"])
            or _resolve_install_key(conn) is None
        )

        print("\n== PLAN DE REPARACIÓN ==")
        if not invalid_branches and not key_invalid and not prefer_name:
            print("Nada que reparar: identidades y clave de instalación válidas.")
            return 0
        for rowid, nombre in invalid_branches:
            print(f"  - Asignar UUIDv7 nuevo a sucursal rowid={rowid} ({nombre!r})")
        if key_invalid:
            print(f"  - Corregir clave {INSTALLATION_BRANCH_KEY} inválida "
                  f"({before['install_key_value']!r})")
        if prefer_name:
            print(f"  - Fijar sucursal de instalación a la sucursal activa "
                  f"llamada {prefer_name!r}")

        if not apply:
            print("\n(dry-run: no se escribió nada; usa --apply para ejecutar)")
            return 0

        conn.execute("BEGIN IMMEDIATE")

        # 1. Sanear identidad de sucursales inválidas (por rowid).
        minted: dict[int, str] = {}
        for rowid, nombre in invalid_branches:
            bid = new_uuid()
            conn.execute(
                "UPDATE sucursales SET id=? WHERE rowid=?", (bid, rowid)
            )
            minted[rowid] = bid
            print(f"  ✔ sucursal rowid={rowid} ({nombre!r}) → id={bid}")

        # 2. Corregir la clave de instalación.
        target: tuple[str, str] | None = None
        if prefer_name:
            row = conn.execute(
                f"SELECT id, nombre FROM sucursales WHERE {VALID_ID_SQL} "
                "AND COALESCE(activa,1)=1 AND TRIM(nombre)=? ORDER BY rowid LIMIT 1",
                (prefer_name.strip(),),
            ).fetchone()
            if not row:
                print(f"  ✘ No existe sucursal activa llamada {prefer_name!r}; rollback.")
                conn.execute("ROLLBACK")
                return 3
            target = (str(row[0]), str(row[1]))
        elif key_invalid:
            row = conn.execute(
                f"SELECT id, nombre FROM sucursales WHERE {VALID_ID_SQL} "
                "AND COALESCE(activa,1)=1 ORDER BY rowid LIMIT 1"
            ).fetchone()
            if row:
                target = (str(row[0]), str(row[1]))

        if target:
            cur = conn.execute(
                "UPDATE configuraciones SET valor=? WHERE clave=?",
                (target[0], INSTALLATION_BRANCH_KEY),
            )
            if cur.rowcount == 0:
                cols = [c[1] for c in conn.execute(
                    "PRAGMA table_info(configuraciones)").fetchall()]
                if "id" in cols:
                    conn.execute(
                        "INSERT INTO configuraciones (id, clave, valor) VALUES (?, ?, ?)",
                        (new_uuid(), INSTALLATION_BRANCH_KEY, target[0]),
                    )
                else:
                    conn.execute(
                        "INSERT INTO configuraciones (clave, valor) VALUES (?, ?)",
                        (INSTALLATION_BRANCH_KEY, target[0]),
                    )
            print(f"  ✔ {INSTALLATION_BRANCH_KEY} → {target[0]} ({target[1]})")
        elif key_invalid:
            print("  ⚠ Clave inválida pero no hay sucursal activa válida para "
                  "asignar; la clave queda como está. Crea una sucursal primero.")

        # 3. Verificación final antes de confirmar.
        remaining = conn.execute(
            f"SELECT COUNT(*) FROM sucursales WHERE {INVALID_ID_SQL}"
        ).fetchone()[0]
        resolved = _resolve_install_key(conn)
        if remaining:
            print(f"  ✘ Persisten {remaining} sucursales inválidas; rollback.")
            conn.execute("ROLLBACK")
            return 3
        conn.execute("COMMIT")

        after = _snapshot(conn)
        _print_snapshot("DESPUÉS", after)
        if resolved:
            print(f"\n✔ Clave de instalación resuelve a sucursal activa: "
                  f"{resolved[1]} ({resolved[0]})")
        else:
            print("\n⚠ La clave de instalación sigue sin resolver a una sucursal "
                  "activa. Configúrala en Configuración → Empresa.")
        return 0
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repara sucursales con id inválido y la clave de instalación.")
    parser.add_argument("--db", required=True, help="Ruta al archivo SQLite.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo reportar (default).")
    parser.add_argument("--apply", action="store_true",
                        help="Aplicar la reparación.")
    parser.add_argument("--prefer-name", default=None,
                        help="Nombre exacto de la sucursal a fijar como instalación.")
    args = parser.parse_args()
    if args.apply and args.dry_run:
        parser.error("--apply y --dry-run son mutuamente excluyentes.")
    return repair(args.db, apply=args.apply, prefer_name=args.prefer_name)


if __name__ == "__main__":
    sys.exit(main())
