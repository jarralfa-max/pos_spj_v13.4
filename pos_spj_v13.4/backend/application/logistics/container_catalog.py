"""Catálogo de contenedores de Logística (integración Logística 32cfbf).

Antes el alta de tipos y contenedores sólo vivía dentro de «Compra en origen» y
exigía un embarque abierto. Este servicio es la ÚNICA puerta del catálogo: la
usan Logística → Contenedores y el embarque (alta contextual). No guarda nada
por su cuenta: delega en `LogisticsApplicationService`, que autoriza, audita y
registra la operación.
"""

from __future__ import annotations

from backend.domain.logistics.container_codes import prefix_for_category
from backend.domain.logistics.entities import ContainerType, PhysicalContainer
from backend.domain.logistics.enums import ContainerCategory, ContainerOwnerType
from backend.shared.ids import new_uuid

CONTAINER_CATEGORY_ES = {
    "MASTER_CONTAINER": "Contenedor maestro", "TRAILER_CONTAINER": "Caja de tráiler",
    "PALLET": "Tarima", "CAGE": "Jaula", "CRATE": "Rejilla", "PLASTIC_BOX": "Caja plástica",
    "CARDBOARD_BOX": "Caja de cartón", "TOTE": "Contenedor apilable", "COOLER": "Hielera",
    "TRAY": "Charola", "BAG": "Bolsa", "BIN": "Contenedor a granel",
}


class ContainerCatalogService:
    def __init__(self, logistics_service, connection) -> None:
        self._logistics = logistics_service
        self._conn = connection

    def container_types(self) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT id, name, category FROM logistics_container_types WHERE active=1"
            " ORDER BY name").fetchall()
        return [(r[0], f"{r[1]} ({CONTAINER_CATEGORY_ES.get(r[2], r[2])})") for r in rows]

    def register_container_type(self, *, actor_user_id, code, name, category,
                                allows_children=False, maximum_net_weight=None,
                                seal_required=False, tare_weight="0") -> str:
        item = ContainerType.create(
            code=code, name=name, category=ContainerCategory(category),
            allows_children=bool(allows_children),
            maximum_children=None, maximum_depth_below=2 if allows_children else 0,
            default_tare_weight=str(tare_weight or "0"),
            maximum_net_weight=str(maximum_net_weight) if maximum_net_weight else None,
            seal_required=bool(seal_required))
        return self._logistics.register_type(actor_user_id=actor_user_id, item=item)

    #: Tope de un alta en lote (comprar 50 cajas iguales es lo habitual).
    MAX_BATCH = 500

    def register_container(self, *, actor_user_id, container_type_id, tare_weight=None,
                           quantity=1, serial_number=None, capacity_weight=None) -> dict:
        """Alta de uno o varios contenedores iguales. El CÓDIGO lo asigna el
        sistema (`<prefijo de la categoría>-<número>`); cada uno nace con su QR
        permanente. Cada contenedor es su propia operación (atómica)."""
        ctype = self._logistics.get_type(container_type_id)
        if ctype is None:
            raise ValueError("Elige el tipo de contenedor")
        try:
            cantidad = int(1 if quantity in (None, "") else quantity)
        except (TypeError, ValueError) as exc:
            raise ValueError("La cantidad debe ser un número entero") from exc
        if not 1 <= cantidad <= self.MAX_BATCH:
            raise ValueError(f"La cantidad debe estar entre 1 y {self.MAX_BATCH}")
        if serial_number and cantidad > 1:
            raise ValueError("El número de serie es de UN contenedor: regístralos de uno en uno")
        prefijo = prefix_for_category(ctype.category.value)
        tara = (str(tare_weight) if tare_weight not in (None, "")
                else str(ctype.default_tare_weight))
        ids, codigos = [], []
        for _ in range(cantidad):
            container: PhysicalContainer = PhysicalContainer.create(
                container_code="", container_type_id=container_type_id,
                owner_type=ContainerOwnerType.COMPANY, tare_weight=tara,
                serial_number=(serial_number or None),
                capacity_weight=(str(capacity_weight) if capacity_weight not in (None, "")
                                 else None))
            result = self._logistics.register_container(
                actor_user_id=actor_user_id, container=container, operation_id=new_uuid(),
                code_prefix=prefijo)
            ids.append(result["container_id"])
            codigos.append(result["code"])
        return {"container_id": ids[0], "code": codigos[0], "container_ids": ids,
                "codes": codigos}

    def next_code_preview(self, container_type_id: str | None = None,
                          category: str | None = None) -> str:
        """El código que tendría el siguiente contenedor de ese tipo (o de esa
        categoría, para un tipo aún no creado). Sólo para mostrarlo: el
        definitivo se asigna al guardar."""
        ctype = self._logistics.get_type(container_type_id) if container_type_id else None
        prefijo = prefix_for_category(ctype.category.value if ctype else category)
        return self._logistics.next_container_code(prefijo)

    def update_container(self, *, actor_user_id, container_id, tare_weight=None,
                         capacity_weight=None, serial_number=None, location_id=None) -> None:
        self._logistics.update_container(
            actor_user_id=actor_user_id, container_id=container_id, operation_id=new_uuid(),
            tare_weight=tare_weight, capacity_weight=capacity_weight,
            serial_number=serial_number, current_location_id=location_id)

    def set_status(self, *, actor_user_id, container_id, status, reason) -> None:
        self._logistics.set_container_status(
            actor_user_id=actor_user_id, container_id=container_id, status=status,
            reason=reason, operation_id=new_uuid())

    def find_by_code(self, code: str):
        row = self._conn.execute(
            "SELECT id FROM logistics_physical_containers WHERE container_code=?",
            ((code or "").strip().upper(),)).fetchone()
        return row[0] if row else None
