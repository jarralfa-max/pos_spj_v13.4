#!/usr/bin/env python3
"""
provision_default_warehouses.py — Crea el almacén principal de cada sucursal (§P0-E).

CLAUDE.md prohíbe warehouse_id=branch_id, pero los puentes de Ventas/Producción/
Compras recurren a esa sustitución hoy porque ninguna sucursal tiene un almacén
real: ninguna migración, seed ni bootstrap crea uno, y la UI de Almacenes todavía
no tiene acción de alta. Este script es el prerrequisito antes de poder repuntar
esos puentes: crea, para cada sucursal sin almacén, uno CENTRAL con las 4 banderas
de asignación activas (ventas/compras/producción/cuarentena) y sus 8 ubicaciones
técnicas (RECEIVING/AVAILABLE/PICKING/QUARANTINE/DAMAGED/TRANSIT/RETURNS/PRODUCTION),
vía ProvisionDefaultWarehouseUseCase — idempotente por sucursal.

No fabrica identidad: requiere --actor-user-id explícito (el operador que corre
el script), nunca "system"/"admin" por default.

Uso:
    python scripts/provision_default_warehouses.py --actor-user-id <uuid> [--db path] [--apply]

    --apply   Aplica los cambios (sin --apply solo reporta qué sucursales carecen
              de almacén, sin escribir nada).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.application.inventory.use_cases import ProvisionDefaultWarehouseUseCase
from backend.application.inventory.use_cases.provision_default_warehouse import (
    default_warehouse_code,
)

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "pos_spj.db")


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def branches_without_warehouse(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT s.id, s.nombre
        FROM sucursales s
        WHERE COALESCE(s.activa, 1) = 1
          AND NOT EXISTS (
              SELECT 1 FROM warehouses w WHERE w.branch_id = s.id
          )
        ORDER BY s.nombre
        """
    ).fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Provisiona el almacén principal de cada sucursal sin uno")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta a la BD SQLite")
    parser.add_argument("--actor-user-id", required=True,
                        help="UUID del usuario que ejecuta el script (auditoría; nunca fabricado)")
    parser.add_argument("--apply", action="store_true",
                        help="Aplicar los cambios (sin esta bandera solo reporta)")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: BD no encontrada: {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = get_conn(args.db)
    pending = branches_without_warehouse(conn)

    if not pending:
        print("✅ Todas las sucursales activas ya tienen almacén principal.")
        conn.close()
        sys.exit(0)

    print(f"{'='*60}")
    print(f"  {len(pending)} sucursal(es) sin almacén principal:")
    print(f"{'='*60}")
    for branch in pending:
        print(f"  - {branch['nombre']} ({branch['id']}) → código propuesto: "
              f"{default_warehouse_code(branch['id'])}")

    if not args.apply:
        print("\nEjecuta con --apply para crear los almacenes y sus ubicaciones técnicas.")
        conn.close()
        sys.exit(0)

    print("\n🔧 Aplicando...")
    use_case = ProvisionDefaultWarehouseUseCase()
    ok_count, fail_count = 0, 0
    for branch in pending:
        result = use_case.execute(
            conn, branch_id=branch["id"], branch_name=branch["nombre"],
            actor_user_id=args.actor_user_id)
        if result.success:
            ok_count += 1
            print(f"  ✓ {branch['nombre']}: almacén {result.entity_id} "
                  f"({len(result.data.get('locations', {}))} ubicaciones técnicas)")
        else:
            fail_count += 1
            print(f"  ✗ {branch['nombre']}: {result.message} [{result.error_code}]",
                  file=sys.stderr)
    conn.commit()
    conn.close()
    print(f"\n✅ {ok_count} sucursal(es) provisionadas, {fail_count} error(es).")
    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
