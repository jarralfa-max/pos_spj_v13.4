from __future__ import annotations

import logging

logger = logging.getLogger("wa.erp")


class PaymentGateway:
    def __init__(self, bridge):
        self._bridge = bridge

    def register_advance(self, venta_id: int, monto: float, metodo: str = "mercadopago") -> int:
        if self._bridge._use_api:
            try:
                data = self._bridge._api_post("/api/v1/anticipos", {
                    "venta_id": venta_id, "monto": monto, "metodo": metodo,
                })
                return data["anticipo_id"]
            except Exception as exc:
                self._bridge._handle_api_write_failure("registrar_anticipo", exc)

        self._bridge._assert_sqlite_write_allowed("registrar_anticipo")
        cursor = self._bridge.db.execute("""
            INSERT INTO anticipos (venta_id, monto, metodo, estado, fecha)
            VALUES (?, ?, ?, 'pendiente', datetime('now'))
        """, (venta_id, monto, metodo))
        self._bridge.db.commit()
        return cursor.lastrowid

    def confirm_payment(self, venta_id: int, monto: float, referencia: str = "", metodo: str = "mercadopago") -> bool:
        if self._bridge._use_api:
            try:
                row = self._bridge.db.execute(
                    "SELECT id FROM anticipos WHERE venta_id=? AND estado='pendiente' LIMIT 1",
                    (venta_id,)
                ).fetchone()
                if row:
                    self._bridge._api_post(f"/api/v1/anticipos/{row[0]}/confirmar", {
                        "monto": monto, "referencia": referencia, "metodo": metodo,
                    })
                    return True
            except Exception as exc:
                self._bridge._handle_api_write_failure("confirmar_pago_anticipo", exc)

        self._bridge._assert_sqlite_write_allowed("confirmar_pago_anticipo")
        try:
            self._bridge.db.execute("""
                UPDATE anticipos SET estado='pagado', fecha_pago=datetime('now'),
                    referencia=? WHERE venta_id=? AND estado='pendiente'
            """, (referencia, venta_id))
            self._bridge.db.execute(
                "UPDATE ventas SET estado='confirmada', anticipo_pagado=? WHERE id=?",
                (monto, venta_id)
            )
            self._bridge.db.commit()
            return True
        except Exception as e:
            logger.warning("confirmar_pago_anticipo: %s", e)
            return False
