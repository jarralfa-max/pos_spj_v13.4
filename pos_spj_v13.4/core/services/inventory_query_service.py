from __future__ import annotations


def get_recent_movements(db, branch_id: int, limit: int = 200):
    try:
        return db.execute(
            "SELECT im.created_at, p.nombre, im.movement_type, im.quantity, im.branch_id, "
            "COALESCE(im.reference_type,''), COALESCE(im.user_name,''), COALESCE(im.source_module,'') "
            "FROM inventory_movements im JOIN productos p ON p.id=im.product_id "
            "WHERE im.branch_id=? ORDER BY im.created_at DESC LIMIT ?",
            [branch_id, int(limit)]
        ).fetchall()
    except Exception:
        return []


def get_inventory_feed_movements(db, branch_id: int, limit: int = 12) -> list[dict]:
    rows = get_recent_movements(db, branch_id, limit)
    return [
        {
            "created_at": row[0],
            "nombre": row[1],
            "movement_type": row[2],
            "quantity": row[3],
            "branch_id": row[4],
            "reference_type": row[5],
            "usuario": row[6],
            "source_module": row[7],
        }
        for row in rows
    ]


def get_product_movement_history(db, product_id: int, branch_id: int, limit: int = 100):
    try:
        return db.execute(
            "SELECT created_at, movement_type, quantity, COALESCE(user_name,''), "
            "COALESCE(reference_type,''), COALESCE(operation_id,'') "
            "FROM inventory_movements "
            "WHERE product_id=? AND branch_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            [product_id, branch_id, int(limit)]
        ).fetchall()
    except Exception:
        return []


def get_inventory_product_rows(db, branch_id: int):
    try:
        return db.execute(
            "SELECT p.id, p.nombre, COALESCE(p.categoria,''), "
            "COALESCE(s.quantity, 0), "
            "COALESCE(p.stock_minimo, 5), COALESCE(s.unit, p.unidad, 'pza') "
            "FROM productos p "
            "LEFT JOIN inventory_stock s "
            "    ON s.product_id=p.id AND s.branch_id=? "
            "WHERE p.activo=1 ORDER BY p.nombre",
            [branch_id]
        ).fetchall()
    except Exception:
        return []


def get_inventory_last_movement_map(db, branch_id: int) -> dict[int, str]:
    try:
        rows = db.execute(
            "SELECT product_id, MAX(created_at) "
            "FROM inventory_movements WHERE branch_id=? "
            "GROUP BY product_id",
            [branch_id]
        ).fetchall()
        return {int(row[0]): str(row[1] or "")[:16] for row in rows}
    except Exception:
        return {}


def get_inventory_operational_kpis(db, branch_id: int, prod_data: list[dict]) -> dict:
    stock_bajo = sum(1 for p in prod_data if p.get("health") == "BAJO MÍN.")
    sin_stock = sum(1 for p in prod_data if p.get("health") == "SIN STOCK")
    virtual_disponible = 0  # fallback seguro hasta backend de virtual
    reservados = 0          # fallback seguro hasta backend de reservas
    mov_hoy = 0
    try:
        r = db.execute(
            "SELECT COUNT(*) FROM inventory_movements WHERE branch_id=? AND DATE(created_at)=DATE('now')",
            [branch_id]
        ).fetchone()
        mov_hoy = int((r[0] if r else 0) or 0)
    except Exception:
        mov_hoy = 0
    return {
        "stock_bajo": stock_bajo,
        "sin_stock_fisico": sin_stock,
        "virtual_disponible": virtual_disponible,
        "reservados": reservados,
        "mov_hoy": mov_hoy,
    }
