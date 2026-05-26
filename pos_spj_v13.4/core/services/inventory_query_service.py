from __future__ import annotations


def get_recent_movements(db, branch_id: int, limit: int = 200):
    try:
        rows = db.execute(
            "SELECT im.created_at, p.nombre, im.movement_type, im.quantity, im.branch_id, "
            "COALESCE(im.reference,''), COALESCE(im.usuario,''), COALESCE(im.origin,'') "
            "FROM inventory_movements im JOIN productos p ON p.id=im.product_id "
            "WHERE im.branch_id=? ORDER BY im.created_at DESC LIMIT ?",
            [branch_id, int(limit)]
        ).fetchall()
        return rows
    except Exception:
        return []


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
