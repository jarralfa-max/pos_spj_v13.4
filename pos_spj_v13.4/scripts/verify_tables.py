"""
verify_tables.py — pos_spj v13.4
Verifica que las tablas críticas existan en la DB.
Expone verificar_tablas(db_path) para uso desde bootstrap_db.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TABLAS_CRITICAS = [
    "productos", "clientes", "ventas", "detalle_ventas",
    "sucursales", "usuarios", "empleados", "proveedores",
    "categorias", "inventario",
]

_EQUIVALENCIAS = {
    "inventario": {"inventario", "branch_inventory"},
    "detalle_ventas": {"detalle_ventas", "venta_items", "sale_items"},
}


def verificar_tablas(db_path: str) -> dict:
    """
    Verifica que las tablas críticas existan en la DB.
    Retorna dict con: cobertura_pct, faltantes, total_criticas, existentes.
    Compatible con lo que bootstrap_database() espera.
    """
    try:
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existentes = {r[0] for r in cur.fetchall()}
        finally:
            conn.close()
    except Exception as e:
        return {"error": str(e), "cobertura_pct": 0, "faltantes": TABLAS_CRITICAS,
                "total_criticas": len(TABLAS_CRITICAS), "existentes": []}

    faltantes = []
    for tabla in TABLAS_CRITICAS:
        opciones = _EQUIVALENCIAS.get(tabla, {tabla})
        if not (existentes & opciones):
            faltantes.append(tabla)

    total = len(TABLAS_CRITICAS)
    presentes = total - len(faltantes)
    cobertura = round(presentes / total * 100, 1) if total else 100.0

    return {
        "cobertura_pct": cobertura,
        "faltantes": faltantes,
        "total_criticas": total,
        "existentes": sorted(existentes),
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Verificar tablas — pos_spj v13.4")
    parser.add_argument("--db", default="pos_spj.db", help="Ruta al archivo SQLite")
    args = parser.parse_args()

    resultado = verificar_tablas(args.db)
    if "error" in resultado:
        print(f"ERROR: {resultado['error']}")
        return 1

    faltantes = resultado["faltantes"]
    cobertura = resultado["cobertura_pct"]
    if faltantes:
        print(f"ADVERTENCIA: Tablas faltantes ({len(faltantes)}): {faltantes}")
        print(f"Cobertura: {cobertura}%")
    else:
        print(f"OK: {resultado['total_criticas']} tablas críticas verificadas ({cobertura}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
