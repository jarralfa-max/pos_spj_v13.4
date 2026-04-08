"""
verify_tables.py — pos_spj v13.4
Verifica que las tablas críticas existen en la base de datos SQLite.

Uso:
    python scripts/verify_tables.py --db pos_spj.db
    python scripts/verify_tables.py --db pos_spj.db --json
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

TABLAS_CRITICAS = [
    # Ventas
    "ventas", "venta_items", "cotizaciones", "cotizacion_items",
    # Inventario
    "inventario", "movimientos_inventario",
    # Compras
    "compras", "compra_items", "ordenes_compra",
    # Finanzas
    "cuentas_por_cobrar", "cuentas_por_pagar",
    # Clientes/Proveedores
    "clientes", "proveedores",
    # Productos
    "productos", "categorias",
    # RRHH
    "empleados", "nomina",
    # Caja/Tesorería
    "cajas", "movimientos_caja", "treasury_ledger",
    # Producción
    "recetas", "receta_ingredientes", "mermas",
    # Delivery
    "pedidos_delivery",
    # Transferencias multisucursal
    "transferencias",
    # Audit
    "audit_log", "event_log",
    # Sucursales
    "sucursales",
    # Finanzas avanzadas (v13.4)
    "financial_event_log",
    # Producción cárnica
    "meat_production_runs", "meat_production_yields",
    # Sync
    "sync_outbox", "sync_state",
]


def verificar_tablas(db_path: str) -> dict:
    """Verifica tablas en la DB. Devuelve dict con presentes/faltantes."""
    if not Path(db_path).exists():
        return {"error": f"DB no encontrada: {db_path}", "presentes": [], "faltantes": TABLAS_CRITICAS}

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        existing = {r[0] for r in cur.fetchall()}
    finally:
        conn.close()

    presentes = [t for t in TABLAS_CRITICAS if t in existing]
    faltantes = [t for t in TABLAS_CRITICAS if t not in existing]
    extras = sorted(existing - set(TABLAS_CRITICAS))

    return {
        "presentes": presentes,
        "faltantes": faltantes,
        "extras": extras,
        "total_criticas": len(TABLAS_CRITICAS),
        "cobertura_pct": round(len(presentes) / len(TABLAS_CRITICAS) * 100, 1),
    }


def main():
    parser = argparse.ArgumentParser(description="Verifica tablas críticas en la DB")
    parser.add_argument("--db", required=True, help="Ruta al archivo SQLite")
    parser.add_argument("--json", action="store_true", help="Salida en JSON")
    args = parser.parse_args()

    resultado = verificar_tablas(args.db)

    if args.json:
        print(json.dumps(resultado, indent=2))
        return 1 if resultado.get("faltantes") else 0

    if "error" in resultado:
        print(f"[ERROR] {resultado['error']}")
        return 1

    print(f"=== VERIFICACIÓN DE TABLAS — {args.db} ===\n")
    print(f"  Cobertura: {resultado['cobertura_pct']}% ({len(resultado['presentes'])}/{resultado['total_criticas']})\n")

    if resultado["faltantes"]:
        print(f"[FALTANTES] ({len(resultado['faltantes'])}):")
        for t in resultado["faltantes"]:
            print(f"  ✗ {t}")
    else:
        print("[OK] Todas las tablas críticas presentes")

    if resultado["extras"]:
        print(f"\n[INFO] Tablas adicionales en DB ({len(resultado['extras'])}):")
        for t in resultado["extras"][:20]:
            print(f"  + {t}")
        if len(resultado["extras"]) > 20:
            print(f"  ... y {len(resultado['extras']) - 20} más")

    return 1 if resultado["faltantes"] else 0


if __name__ == "__main__":
    sys.exit(main())
