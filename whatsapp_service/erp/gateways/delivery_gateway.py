from __future__ import annotations

import logging

logger = logging.getLogger("wa.erp")


class DeliveryGateway:
    def __init__(self, bridge):
        self._bridge = bridge

    def schedule(self, venta_id: int, direccion: str, fecha_entrega: str = "", telefono_cliente: str = "") -> bool:
        if self._bridge._use_api:
            try:
                self._bridge._api_patch(
                    f"/api/v1/pedidos/{venta_id}/estado",
                    estado="confirmado",
                    notas=f"delivery:{direccion}",
                )
            except Exception as exc:
                self._bridge._handle_api_write_failure("programar_delivery", exc)

        self._bridge._assert_sqlite_write_allowed("programar_delivery")
        try:
            self._bridge.db.execute("""
                UPDATE ventas SET tipo_entrega='domicilio',
                    direccion_entrega=?,
                    fecha_entrega_programada=COALESCE(NULLIF(?,''),(datetime('now','+1 day')))
                WHERE id=?
            """, (direccion, fecha_entrega, venta_id))
            self._bridge.db.commit()
            return True
        except Exception as e:
            logger.warning("programar_delivery: %s", e)
            return False
