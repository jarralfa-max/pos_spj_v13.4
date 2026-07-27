#!/usr/bin/env python3
"""
reconcile_inventory.py — Detecta y corrige divergencias entre las 3 tablas de stock.

Fuente de verdad: movimientos_inventario (append-only, inmutable).
Las 3 tablas a reconciliar:
  1. productos.existencia       — suma global (todas las sucursales)
  2. inventario_actual          — por sucursal (cache rápido)
  3. branch_inventory           — por sucursal (leída por POS en tiempo real)

Uso:
    python scripts/reconcile_inventory.py [--db path/to/pos_spj.db] [--fix] [--quiet]

    --fix     Aplicar correcciones automáticamente (sin --fix solo reporta)
    --quiet   Solo imprimir divergencias, no el resumen final
"""
from __future__ import annotations
import argparse
import sqlite3
import sys
import os
from datetime import datetime

DEFAULT_DB = os.path.join(os.path.dirname(__file__), "..", "pos_spj.db")


def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def detect_divergences(conn: sqlite3.Connection) -> list[dict]:
    """
    Retorna lista de productos con divergencia entre tablas.
    Compara:
      - productos.existencia  vs  SUM(inventario_actual.cantidad)
      - SUM(inventario_actual) vs  SUM(branch_inventory.quantity)
    """
    rows = conn.execute("""
        SELECT
            p.id                                          AS producto_id,
            COALESCE(p.nombre, p.descripcion, '')         AS nombre,
            COALESCE(p.existencia, 0)                     AS glob,
            COALESCE(ia_agg.ia_sum, 0)                    AS ia_sum,
            COALESCE(bi_agg.bi_sum, 0)                    AS bi_sum
        FROM productos p
        LEFT JOIN (
            SELECT producto_id, SUM(cantidad) AS ia_sum
            FROM inventario_actual
            GROUP BY producto_id
        ) ia_agg ON ia_agg.producto_id = p.id
        LEFT JOIN (
            SELECT product_id, SUM(quantity) AS bi_sum
            FROM branch_inventory
            GROUP BY product_id
        ) bi_agg ON bi_agg.product_id = p.id
        WHERE ABS(COALESCE(p.existencia, 0) - COALESCE(ia_agg.ia_sum, 0)) > 0.01
           OR ABS(COALESCE(ia_agg.ia_sum, 0) - COALESCE(bi_agg.bi_sum, 0)) > 0.01
        ORDER BY p.id
    """).fetchall()
    return [dict(r) for r in rows]


def compute_truth_from_movements(conn: sqlite3.Connection, producto_id: int) -> dict[int, float]:
    """
    Calcula el stock real por sucursal sumando movimientos_inventario.
    ENTRADA = +qty, SALIDA = -qty
    """
    rows = conn.execute("""
        SELECT sucursal_id,
               SUM(CASE tipo WHEN 'ENTRADA' THEN cantidad ELSE -cantidad END) AS stock
        FROM movimientos_inventario
        WHERE producto_id = ?
        GROUP BY sucursal_id
    """, (producto_id,)).fetchall()
    return {r["sucursal_id"]: max(0.0, float(r["stock"] or 0)) for r in rows}


def apply_fix(conn: sqlite3.Connection, producto_id: int, nombre: str) -> None:
    """
    Corrige las 3 tablas usando movimientos_inventario como fuente de verdad.
    """
    truth = compute_truth_from_movements(conn, producto_id)
    if not truth:
        # Sin movimientos registrados — usar productos.existencia como fallback
        row = conn.execute(
            "SELECT COALESCE(existencia, 0) FROM productos WHERE id=?", (producto_id,)
        ).fetchone()
        glob = float(row[0]) if row else 0.0
        truth = {1: glob}

    for sucursal_id, qty in truth.items():
        avg_cost_row = conn.execute("""
            SELECT AVG(costo_unitario) FROM movimientos_inventario
            WHERE producto_id=? AND sucursal_id=? AND tipo='ENTRADA' AND costo_unitario > 0
        """, (producto_id, sucursal_id)).fetchone()
        avg_cost = float(avg_cost_row[0] or 0) if avg_cost_row else 0.0

        # Corregir inventario_actual
        conn.execute("""
            INSERT INTO inventario_actual (producto_id, sucursal_id, cantidad, costo_promedio)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(producto_id, sucursal_id) DO UPDATE SET
                cantidad             = excluded.cantidad,
                costo_promedio       = excluded.costo_promedio,
                ultima_actualizacion = datetime('now')
        """, (producto_id, sucursal_id, qty, avg_cost))

        # Corregir branch_inventory
        conn.execute("""
            INSERT INTO branch_inventory (product_id, branch_id, quantity, updated_at)
            VALUES (?, ?, ?, datetime('now'))
            ON CONFLICT(product_id, branch_id) DO UPDATE SET
                quantity   = excluded.quantity,
                updated_at = excluded.updated_at
        """, (producto_id, sucursal_id, qty))

    # Corregir productos.existencia = suma global
    conn.execute("""
        UPDATE productos
        SET existencia = (
            SELECT COALESCE(SUM(cantidad), 0)
            FROM inventario_actual WHERE producto_id = ?
        )
        WHERE id = ?
    """, (producto_id, producto_id))

    # Registrar movimiento de auditoría
    import uuid
    conn.execute("""
        INSERT INTO movimientos_inventario
            (uuid, producto_id, tipo, tipo_movimiento, cantidad,
             descripcion, referencia, usuario, sucursal_id, fecha)
        VALUES (?, ?, 'AJUSTE', 'RECONCILIACION', 0,
                'Reconciliación automática de inventario', 'RECON', 'sistema', 1, datetime('now'))
    """, (str(uuid.uuid4()), producto_id))


def check_vs_movements(conn: sqlite3.Connection) -> list[dict]:
    """
    Compare inventario_actual per branch against movement ledger reconstruction.
    Returns rows where the materialised value differs from the ledger sum.
    """
    try:
        rows = conn.execute(
            """
            SELECT ia.producto_id,
                   ia.sucursal_id,
                   COALESCE(p.nombre, '') AS nombre,
                   COALESCE(p.unidad,'kg') AS unidad,
                   COALESCE(ia.cantidad, 0) AS saldo_mat,
                   COALESCE(saldo.saldo_mov, 0) AS saldo_mov,
                   COALESCE(ia.cantidad, 0) - COALESCE(saldo.saldo_mov, 0) AS diferencia
            FROM inventario_actual ia
            JOIN productos p ON p.id = ia.producto_id
            LEFT JOIN (
                SELECT producto_id, sucursal_id,
                       SUM(CASE
                           WHEN tipo IN ('ENTRADA','PRODUCCION','DEVOLUCION') THEN cantidad
                           WHEN tipo IN ('SALIDA','MERMA','TRASPASO','AJUSTE') THEN -cantidad
                           ELSE 0
                       END) AS saldo_mov
                FROM movimientos_inventario
                GROUP BY producto_id, sucursal_id
            ) saldo ON saldo.producto_id = ia.producto_id
                    AND saldo.sucursal_id = ia.sucursal_id
            WHERE ABS(COALESCE(ia.cantidad,0) - COALESCE(saldo.saldo_mov,0)) > 0.001
            ORDER BY ABS(diferencia) DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception as exc:
        print(f"ERROR check_vs_movements: {exc}", file=sys.stderr)
        return []


def repair_from_movements(conn: sqlite3.Connection, mismatches: list[dict]) -> int:
    """Correct inventario_actual.cantidad to match the movement ledger. Returns fixed count."""
    import uuid as _uuid
    fixed = 0
    for row in mismatches:
        try:
            conn.execute(
                """
                UPDATE inventario_actual
                SET cantidad = ?, ultima_actualizacion = datetime('now')
                WHERE producto_id = ? AND sucursal_id = ?
                """,
                (float(row["saldo_mov"]), int(row["producto_id"]), int(row["sucursal_id"])),
            )
            conn.execute(
                """
                INSERT INTO movimientos_inventario
                    (uuid, producto_id, tipo, tipo_movimiento, cantidad,
                     descripcion, referencia, usuario, sucursal_id, fecha)
                VALUES (?, ?, 'AJUSTE', 'RECONCILIACION', 0,
                        'Reparación automática de inventario_actual', 'REPAIR',
                        'sistema', ?, datetime('now'))
                """,
                (str(_uuid.uuid4()), int(row["producto_id"]), int(row["sucursal_id"])),
            )
            fixed += 1
        except Exception as exc:
            print(f"  ERROR repair producto_id={row['producto_id']} sucursal={row['sucursal_id']}: {exc}", file=sys.stderr)
    conn.commit()
    return fixed


def main():
    parser = argparse.ArgumentParser(description="Reconcilia tablas de inventario")
    parser.add_argument("--db", default=DEFAULT_DB, help="Ruta a la BD SQLite")
    parser.add_argument("--fix", action="store_true", help="Aplicar correcciones (modo legacy)")
    parser.add_argument("--check", action="store_true", help="Verificar vs ledger de movimientos")
    parser.add_argument("--repair", action="store_true", help="Reparar inventario_actual desde ledger")
    parser.add_argument("--backup", action="store_true", help="Crear .bak antes de reparar")
    parser.add_argument("--quiet", action="store_true", help="Solo mostrar divergencias")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"ERROR: BD no encontrada: {args.db}", file=sys.stderr)
        sys.exit(1)

    if (args.repair or args.fix) and args.backup:
        import shutil
        bak = args.db + ".bak"
        shutil.copy2(args.db, bak)
        print(f"Backup creado: {bak}")

    conn = get_conn(args.db)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ── NEW: --check / --repair against movement ledger ─────────────────────
    if args.check or args.repair:
        mismatches = check_vs_movements(conn)
        if not mismatches:
            print("✅ inventario_actual concuerda con ledger de movimientos.")
            if not args.fix:
                sys.exit(0)
        else:
            print(f"⚠️  {len(mismatches)} fila(s) divergen del ledger:")
            fmt = "{:<6} {:<4} {:<25} {:>12} {:>12} {:>10}"
            print(fmt.format("ProdID", "Suc", "Nombre", "materializado", "movimientos", "diferencia"))
            print("-" * 75)
            for row in mismatches:
                print(fmt.format(
                    row["producto_id"], row["sucursal_id"], str(row["nombre"])[:25],
                    f"{float(row['saldo_mat']):.4f}",
                    f"{float(row['saldo_mov']):.4f}",
                    f"{float(row['diferencia']):.4f}",
                ))
            if args.repair:
                fixed = repair_from_movements(conn, mismatches)
                print(f"\n✅ Reparados {fixed}/{len(mismatches)} filas.")
                sys.exit(0 if fixed == len(mismatches) else 1)
            sys.exit(1)
        if not args.fix:
            sys.exit(0)

    if not args.quiet:
        print(f"\n{'='*60}")
        print(f"  Reconciliación de inventario — {timestamp}")
        print(f"  BD: {args.db}")
        print(f"  Modo: {'CORREGIR' if args.fix else 'SOLO REPORTAR'}")
        print(f"{'='*60}\n")

    divergencias = detect_divergences(conn)

    if not divergencias:
        if not args.quiet:
            print("✅ Sin divergencias. Las 3 tablas están sincronizadas.\n")
        sys.exit(0)

    print(f"⚠️  {len(divergencias)} producto(s) con divergencia:\n")
    fmt = "{:<6} {:<30} {:>10} {:>10} {:>10}"
    print(fmt.format("ID", "Nombre", "global", "inv_actual", "branch_inv"))
    print("-" * 70)
    for d in divergencias:
        print(fmt.format(
            d["producto_id"],
            d["nombre"][:30],
            f"{d['glob']:.3f}",
            f"{d['ia_sum']:.3f}",
            f"{d['bi_sum']:.3f}",
        ))

    if args.fix:
        print(f"\n🔧 Aplicando correcciones...")
        fixed = 0
        errors = 0
        for d in divergencias:
            try:
                apply_fix(conn, d["producto_id"], d["nombre"])
                fixed += 1
            except Exception as e:
                print(f"  ERROR producto {d['producto_id']}: {e}", file=sys.stderr)
                errors += 1
        conn.commit()
        print(f"\n✅ {fixed} corregidos, {errors} errores.")

        # Verificar resultado
        remaining = detect_divergences(conn)
        if remaining:
            print(f"\n⚠️  Quedan {len(remaining)} divergencias sin resolver:")
            for d in remaining:
                print(f"  prod_id={d['producto_id']} glob={d['glob']:.3f} "
                      f"ia={d['ia_sum']:.3f} bi={d['bi_sum']:.3f}")
        else:
            print("✅ Verificación post-corrección: 0 divergencias.")
    else:
        print(f"\nEjecuta con --fix para corregir automáticamente.")

    conn.close()


if __name__ == "__main__":
    main()
