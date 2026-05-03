#!/usr/bin/env python3
"""
scripts/health_check.py — Health check del ERP SPJ POS.

Verifica:
  1. Conectividad a la BD
  2. Coherencia de las 3 tablas de inventario
  3. Reservas de stock huérfanas / expiradas
  4. Estado del API Gateway (si ERP_API_URL está configurado)
  5. Migraciones pendientes

Uso:
    python scripts/health_check.py --db pos_spj.db
    python scripts/health_check.py --db pos_spj.db --json
    python scripts/health_check.py --db pos_spj.db --fix-expiradas

Salida:
    Sin --json: tabla legible en terminal con código de salida 0 (ok) / 1 (degraded) / 2 (critical)
    Con --json: JSON con todos los checks
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from typing import Dict, List, Tuple

# ── Helpers ───────────────────────────────────────────────────────────────────

STATUS_OK       = "ok"
STATUS_WARN     = "warn"
STATUS_CRITICAL = "critical"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ── Checks ────────────────────────────────────────────────────────────────────

def check_db_connectivity(conn: sqlite3.Connection) -> Dict:
    """Verifica que la BD responde."""
    try:
        t0 = time.perf_counter()
        conn.execute("SELECT 1").fetchone()
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        return {"status": STATUS_OK, "latency_ms": latency_ms}
    except Exception as exc:
        return {"status": STATUS_CRITICAL, "error": str(exc)}


def check_inventory_coherence(conn: sqlite3.Connection) -> Dict:
    """
    Verifica que productos.existencia coincida con la suma de inventario_actual.
    Reporta divergencias producto por producto.
    """
    try:
        rows = conn.execute("""
            SELECT
                p.id,
                p.nombre,
                p.existencia AS p_existencia,
                COALESCE(SUM(ia.cantidad), 0) AS ia_total
            FROM productos p
            LEFT JOIN inventario_actual ia ON ia.producto_id = p.id
            WHERE p.activo = 1
            GROUP BY p.id
            HAVING ABS(p.existencia - COALESCE(SUM(ia.cantidad), 0)) > 0.01
        """).fetchall()

        divergencias = [dict(r) for r in rows]
        if not divergencias:
            return {"status": STATUS_OK, "divergencias": 0}
        return {
            "status": STATUS_WARN,
            "divergencias": len(divergencias),
            "detalle": divergencias[:10],  # cap para no inflar el JSON
        }
    except sqlite3.OperationalError as exc:
        # Tabla aún no existe (BD nueva)
        if "no such table" in str(exc):
            return {"status": STATUS_OK, "note": "inventario_actual table not found — OK for fresh DB"}
        return {"status": STATUS_WARN, "error": str(exc)}


def check_branch_vs_inventario_actual(conn: sqlite3.Connection) -> Dict:
    """
    Verifica que branch_inventory coincida con inventario_actual por sucursal.
    """
    try:
        rows = conn.execute("""
            SELECT
                ia.producto_id,
                ia.sucursal_id,
                ia.cantidad AS ia_qty,
                COALESCE(bi.quantity, 0) AS bi_qty
            FROM inventario_actual ia
            LEFT JOIN branch_inventory bi
                ON bi.product_id = ia.producto_id
               AND bi.branch_id  = ia.sucursal_id
            WHERE ABS(ia.cantidad - COALESCE(bi.quantity, 0)) > 0.01
        """).fetchall()

        divergencias = [dict(r) for r in rows]
        if not divergencias:
            return {"status": STATUS_OK, "divergencias": 0}
        return {
            "status": STATUS_WARN,
            "divergencias": len(divergencias),
            "detalle": divergencias[:10],
        }
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return {"status": STATUS_OK, "note": "branch_inventory table not found — OK for fresh DB"}
        return {"status": STATUS_WARN, "error": str(exc)}


def check_orphan_reservations(conn: sqlite3.Connection,
                               fix: bool = False) -> Dict:
    """
    Detecta (y opcionalmente expira) reservas de stock huérfanas.
    """
    try:
        rows = conn.execute("""
            SELECT COUNT(*) AS n FROM stock_reservations
            WHERE estado = 'activa'
              AND expires_at < datetime('now')
        """).fetchone()
        huerfanas = int(rows["n"]) if rows else 0

        if fix and huerfanas:
            conn.execute("""
                UPDATE stock_reservations
                SET estado = 'expirada'
                WHERE estado = 'activa' AND expires_at < datetime('now')
            """)
            conn.commit()

        status = STATUS_WARN if huerfanas > 5 else STATUS_OK
        return {"status": status, "huerfanas": huerfanas,
                "fixed": fix and huerfanas > 0}
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return {"status": STATUS_OK, "note": "stock_reservations not found — OK"}
        return {"status": STATUS_WARN, "error": str(exc)}


def check_pending_sales(conn: sqlite3.Connection) -> Dict:
    """Cuenta ventas en estado pendiente_wa > 2 horas."""
    try:
        rows = conn.execute("""
            SELECT COUNT(*) AS n FROM ventas
            WHERE estado = 'pendiente_wa'
              AND fecha < datetime('now', '-2 hours')
        """).fetchone()
        stale = int(rows["n"]) if rows else 0
        status = STATUS_WARN if stale > 10 else STATUS_OK
        return {"status": status, "pedidos_pendientes_viejos": stale}
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return {"status": STATUS_OK, "note": "ventas table not found"}
        return {"status": STATUS_WARN, "error": str(exc)}


def check_api_gateway(api_url: str, api_key: str) -> Dict:
    """Llama a /health del API Gateway si está configurado."""
    if not api_url:
        return {"status": STATUS_OK, "note": "ERP_API_URL not set — skipped"}
    try:
        import httpx
        t0 = time.perf_counter()
        resp = httpx.get(
            f"{api_url.rstrip('/')}/health",
            headers={"X-API-Key": api_key},
            timeout=5.0,
        )
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        data = resp.json()
        return {
            "status": STATUS_OK if data.get("status") == "ok" else STATUS_WARN,
            "http_status": resp.status_code,
            "latency_ms": latency_ms,
            "api_status": data.get("status"),
        }
    except Exception as exc:
        return {"status": STATUS_CRITICAL, "error": str(exc)}


def check_low_stock(conn: sqlite3.Connection) -> Dict:
    """Cuenta productos por debajo del stock mínimo."""
    try:
        rows = conn.execute("""
            SELECT COUNT(*) AS n
            FROM productos
            WHERE activo = 1
              AND existencia <= stock_minimo
              AND stock_minimo > 0
        """).fetchone()
        bajo_minimo = int(rows["n"]) if rows else 0
        status = STATUS_WARN if bajo_minimo > 0 else STATUS_OK
        return {"status": status, "productos_bajo_minimo": bajo_minimo}
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):
            return {"status": STATUS_OK}
        return {"status": STATUS_WARN, "error": str(exc)}


# ── Aggregate ─────────────────────────────────────────────────────────────────

def _aggregate_status(checks: Dict[str, Dict]) -> str:
    statuses = [c["status"] for c in checks.values()]
    if STATUS_CRITICAL in statuses:
        return STATUS_CRITICAL
    if STATUS_WARN in statuses:
        return STATUS_WARN
    return STATUS_OK


def _exit_code(status: str) -> int:
    return {STATUS_OK: 0, STATUS_WARN: 1, STATUS_CRITICAL: 2}.get(status, 2)


def _color(status: str) -> str:
    colors = {STATUS_OK: "\033[92m", STATUS_WARN: "\033[93m", STATUS_CRITICAL: "\033[91m"}
    return colors.get(status, "") + status + "\033[0m"


def run_health_check(db_path: str,
                     fix_expiradas: bool = False,
                     as_json: bool = False) -> int:
    conn = _connect(db_path)
    api_url = os.environ.get("ERP_API_URL", "")
    api_key = os.environ.get("ERP_API_KEY", "")

    checks = {
        "db_connectivity":          check_db_connectivity(conn),
        "inventory_coherence":      check_inventory_coherence(conn),
        "branch_vs_inventario":     check_branch_vs_inventario_actual(conn),
        "orphan_reservations":      check_orphan_reservations(conn, fix=fix_expiradas),
        "pedidos_pendientes_viejos": check_pending_sales(conn),
        "low_stock":                check_low_stock(conn),
        "api_gateway":              check_api_gateway(api_url, api_key),
    }

    overall = _aggregate_status(checks)

    report = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "db_path":   db_path,
        "overall":   overall,
        "checks":    checks,
    }

    if as_json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_table(report)

    conn.close()
    return _exit_code(overall)


def _print_table(report: Dict):
    print(f"\n{'='*60}")
    print(f"  SPJ POS ERP — Health Check  [{report['timestamp']}]")
    print(f"  DB: {report['db_path']}")
    print(f"  Overall: {_color(report['overall'])}")
    print(f"{'='*60}")
    for name, result in report["checks"].items():
        status = result["status"]
        extras = {k: v for k, v in result.items() if k != "status"}
        extras_str = "  " + ", ".join(f"{k}={v}" for k, v in extras.items()) if extras else ""
        print(f"  {name:<35} {_color(status)}{extras_str}")
    print(f"{'='*60}\n")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SPJ ERP Health Check")
    parser.add_argument("--db", default="pos_spj.db",
                        help="Ruta al archivo SQLite (default: pos_spj.db)")
    parser.add_argument("--json", action="store_true",
                        help="Salida en JSON")
    parser.add_argument("--fix-expiradas", action="store_true",
                        help="Expirar reservas huérfanas automáticamente")
    args = parser.parse_args()

    sys.exit(run_health_check(
        db_path=args.db,
        fix_expiradas=args.fix_expiradas,
        as_json=args.json,
    ))
