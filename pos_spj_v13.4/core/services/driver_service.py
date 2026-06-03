from __future__ import annotations

from typing import Any, Dict, List, Optional

from repositories.driver_repository import DriverRepository


class DriverService:
    """Business rules for driver assignment workflows."""

    def __init__(self, db, repository: Optional[DriverRepository] = None):
        self.db = db
        self.repository = repository or DriverRepository(db)


    def list_drivers(self) -> List[Dict[str, Any]]:
        return self.repository.list_drivers()

    def create_driver(self, data: Dict[str, Any]) -> int:
        self._validate_driver_payload(data)
        return self.repository.create_driver(data)

    def update_driver(self, driver_id: int, data: Dict[str, Any]) -> None:
        self._validate_driver_payload(data)
        self.repository.update_driver(driver_id, data)

    def deactivate_driver(self, driver_id: int) -> None:
        self.repository.deactivate_driver(driver_id)

    @staticmethod
    def _validate_driver_payload(data: Dict[str, Any]) -> None:
        if not str(data.get("nombre") or "").strip():
            raise ValueError("El nombre del repartidor es obligatorio")

    def list_active_drivers(self, branch_id: int) -> List[Dict[str, Any]]:
        return self.repository.list_active_drivers(branch_id)

    def assign_driver(self, order_id: int, driver_id: int, user: str = "sistema") -> None:
        order = self._get_order(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        driver = self.repository.get_driver(driver_id)
        if not driver:
            raise ValueError("Repartidor no encontrado")
        if not int(driver.get("activo") or 0):
            raise ValueError("El repartidor no está activo")
        order_branch = int(order.get("sucursal_id") or 1)
        driver_branch = int(driver.get("sucursal_id") or 1)
        if driver_branch not in (0, order_branch):
            raise ValueError("El repartidor pertenece a otra sucursal")
        status = (order.get("estado") or "").lower()
        workflow = self._infer_workflow(order)
        if workflow == "counter":
            raise ValueError("Los pedidos de mostrador no llevan repartidor")
        if workflow == "scheduled":
            raise ValueError("El pedido programado debe activarse antes de asignar repartidor")
        if status != "preparacion":
            raise ValueError("Solo se puede asignar repartidor a pedidos en preparación")
        self.repository.assign_driver(
            order_id,
            driver_id,
            usuario=user,
            notes=f"Repartidor asignado: {driver.get('nombre') or driver_id}",
        )

    def validate_out_for_delivery(self, order_id: int) -> None:
        order = self._get_order(order_id)
        if not order:
            raise ValueError("Pedido no encontrado")
        workflow = self._infer_workflow(order)
        if workflow == "counter":
            raise ValueError("Los pedidos de mostrador no pasan a ruta")
        if workflow == "scheduled":
            raise ValueError("El pedido programado debe activarse antes de enviarse a ruta")
        if not order.get("driver_id"):
            raise ValueError("Para enviar a ruta debes asignar un repartidor")

    def mark_driver_on_route(self, driver_id: int, value: bool) -> None:
        self.repository.mark_driver_on_route(driver_id, value)

    def get_driver_location(self, driver_id: int) -> Optional[Dict[str, Any]]:
        return self.repository.get_driver_location(driver_id)

    def save_driver_location(self, driver_id: int, lat: float, lng: float) -> None:
        self.repository.save_driver_location(driver_id, lat, lng)

    def get_driver_cut_summary(self, driver_id: int, branch_id: int, date_from: str = "", date_to: str = "") -> Dict[str, Any]:
        return self.repository.get_driver_cut_summary(driver_id, branch_id, date_from, date_to)

    def create_driver_cut(self, data: Dict[str, Any]) -> int:
        return self.repository.create_driver_cut(data)

    def _get_order(self, order_id: int) -> Optional[Dict[str, Any]]:
        row = self.db.execute("SELECT * FROM delivery_orders WHERE id=?", (order_id,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def _infer_workflow(order: Dict[str, Any]) -> str:
        workflow = (order.get("workflow_type") or "").lower()
        delivery_type = (order.get("delivery_type") or "").lower()
        status = (order.get("estado") or "").lower()
        scheduled_at = order.get("scheduled_at")
        if workflow:
            return workflow
        if scheduled_at or status in ("programado", "scheduled"):
            return "scheduled"
        if delivery_type in ("pickup", "sucursal"):
            return "counter"
        return "delivery"
