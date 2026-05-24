from __future__ import annotations

from repositories.driver_repository import DriverRepository


class DriverService:
    def __init__(self, db):
        self.db = db
        self.repo = DriverRepository(db)

    def list_active_drivers(self, branch_id: int) -> list[dict]:
        return self.repo.list_active_drivers(branch_id)

    def assign_driver(self, order_id: int, driver_id: int, *, branch_id: int) -> None:
        driver = self.repo.get_driver(driver_id)
        if not driver:
            raise ValueError("El repartidor no existe.")
        if int(driver.get("activo") or 0) != 1:
            raise ValueError("El repartidor no está activo.")
        if int(driver.get("sucursal_id") or 1) != int(branch_id):
            raise ValueError("El repartidor no pertenece a la sucursal actual.")

        order = self.db.execute(
            "SELECT estado, workflow_type FROM delivery_orders WHERE id=?",
            (int(order_id),),
        ).fetchone()
        if not order:
            raise ValueError("Pedido no encontrado.")
        estado = str(order[0] or "").lower()
        workflow = str(order[1] or "").lower()
        if workflow == "counter":
            raise ValueError("No se puede asignar repartidor a pedidos de Mostrador.")
        if workflow == "scheduled":
            raise ValueError("No se puede asignar repartidor a pedidos Programados sin activar.")
        if estado in ("entregado", "cancelado"):
            raise ValueError("No se puede asignar repartidor a pedido entregado/cancelado.")
        if estado != "preparacion":
            raise ValueError("Solo se puede asignar repartidor en estado Preparación.")

        self.repo.assign_driver(order_id, driver_id)
        try:
            self.db.execute(
                "INSERT INTO delivery_order_history(order_id,estado_anterior,estado_nuevo,usuario,observacion) "
                "VALUES(?,?,?,?,?)",
                (int(order_id), estado, estado, "sistema", f"Repartidor asignado: {driver.get('nombre','')}")
            )
            self.db.commit()
        except Exception:
            pass

