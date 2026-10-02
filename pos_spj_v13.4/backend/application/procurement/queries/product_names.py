"""Nombres de producto para las lecturas de Compras (la pantalla nunca muestra
ids). Tolera la ausencia de la tabla del maestro: sin ella, "Producto"."""

from __future__ import annotations

import sqlite3

UNKNOWN_PRODUCT = "Producto"


def product_names(connection, product_ids) -> dict[str, str]:
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    try:
        rows = connection.execute(
            f"SELECT id, name FROM products WHERE id IN ({marks})", ids).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {str(r[0]): str(r[1]) for r in rows if r[1]}


def product_labels(connection, product_ids) -> dict[str, str]:
    """«CAR-000001 · Alas» (§19): lo que Compras muestra de un producto. Mismo
    contrato que `product_names` (sólo los que existen), con el código."""
    ids = sorted({str(pid) for pid in product_ids if pid})
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    try:
        rows = connection.execute(
            f"SELECT id, code, name FROM products WHERE id IN ({marks})", ids).fetchall()
    except sqlite3.OperationalError:
        return product_names(connection, ids)
    labels = {}
    for pid, code, name in rows:
        if not name:
            continue
        code = str(code or "").strip()
        labels[str(pid)] = f"{code} · {name}" if code and code != name else str(name)
    return labels
