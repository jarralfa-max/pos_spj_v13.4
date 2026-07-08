# core/services/recepcion_qr_service.py
"""
RecepcionQRService — escrituras del flujo de recepción por QR (Remediación F).

Ruta canónica: RecepcionQRWidget (UI) → RecepcionQRService → DB. Preserva EXACTAMENTE
la lógica que vivía embebida en el widget (transacción atómica de recepción con
UPSERT de inventario, sync de productos.existencia, movimientos y trazabilidad).
"""
from __future__ import annotations

import json
import logging
import uuid

logger = logging.getLogger("spj.services.recepcion_qr")


class RecepcionQRService:
    def __init__(self, db):
        self.db = db

    # ── Transacción de recepción (inventario + trazabilidad) ────────────────────
    def procesar_recepcion(self, uuid_qr: str, items: list, notas: str,
                           sucursal_id, usuario: str) -> str:
        """Transacción atómica: recepciones + recepcion_items + inventario + movimientos
        + trazabilidad. Devuelve el recepcion_id (UUIDv7). Lógica idéntica a la del
        widget original."""
        from backend.shared.ids import new_uuid
        op_id = str(uuid.uuid4())
        folio = f"REC-{op_id[:8].upper()}"

        _tqr_row = self.db.execute(
            "SELECT COALESCE(datos_extra,'{}') FROM trazabilidad_qr WHERE uuid_qr=?",
            (uuid_qr,)
        ).fetchone()
        datos_extra = json.loads(_tqr_row[0] if _tqr_row else "{}")
        proveedor_id = datos_extra.get("proveedor_id")
        condicion    = datos_extra.get("condicion_pago", "liquidado")
        metodo       = datos_extra.get("metodo_pago", "efectivo")
        monto_pagado = float(datos_extra.get("monto_pagado", 0))
        monto_total  = float(datos_extra.get("monto_total", 0))

        from core.db.connection import transaction as _tx_qr
        recepcion_id = new_uuid()
        with _tx_qr(self.db):
            self.db.execute("""
                INSERT INTO recepciones
                    (id, folio, tipo, proveedor_id, sucursal_id, usuario,
                     notas, operation_id, estado,
                     uuid_qr, condicion_pago, metodo_pago,
                     monto_pagado, monto_total,
                     saldo_pendiente)
                VALUES(?,?,?,?,?,?,?,?,'completada',?,?,?,?,?,?)
            """, (recepcion_id, folio, "COMPRA", proveedor_id, sucursal_id, usuario,
                  notas, op_id, uuid_qr, condicion, metodo,
                  monto_pagado, monto_total,
                  max(0, monto_total - monto_pagado)))

            for item in items:
                prod_id   = item["product_id"]
                qty       = float(item["cantidad"])
                costo     = float(item.get("costo_unitario", 0))
                caducidad = item.get("fecha_caducidad")

                self.db.execute("""
                    INSERT INTO recepcion_items
                        (id, recepcion_id, producto_id, cantidad, costo_unitario,
                         uuid_qr_contenedor, fecha_caducidad)
                    VALUES(?,?,?,?,?,?,?)
                """, (new_uuid(), recepcion_id, prod_id, qty, costo, uuid_qr, caducidad))

                # Costo promedio ponderado — se calcula ANTES de mover (con el
                # estado previo). El STOCK (cantidad) lo actualiza el trigger
                # canónico trg_recalc_inventario_actual al insertar el movimiento;
                # el widget legacy hacía además un UPSERT manual → doble conteo.
                prev = self.db.execute(
                    "SELECT cantidad, costo_promedio FROM inventario_actual "
                    "WHERE producto_id=? AND sucursal_id=?", (prod_id, sucursal_id)
                ).fetchone()
                cant_old  = float(prev[0]) if prev and prev[0] is not None else 0.0
                costo_old = float(prev[1]) if prev and prev[1] is not None else 0.0
                nueva_cant = cant_old + qty
                costo_prom = ((cant_old * costo_old + qty * costo) / nueva_cant
                              if nueva_cant > 0 else costo)

                # Movimiento de inventario (auditoría). Identidad UUIDv7 en `id`
                # (el esquema born-clean usa `id`, no `uuid`). El trigger suma qty
                # a inventario_actual.cantidad.
                self.db.execute("""
                    INSERT INTO movimientos_inventario
                        (id, producto_id, tipo, tipo_movimiento, cantidad,
                         descripcion, referencia, usuario, sucursal_id)
                    VALUES(?,?,'entrada','COMPRA',?,?,?,?,?)
                """, (new_uuid(), prod_id, qty,
                      f"Recepción QR {uuid_qr}", folio, usuario, sucursal_id))

                # Fijar el costo promedio ponderado (la cantidad ya la puso el trigger).
                self.db.execute("""
                    UPDATE inventario_actual
                    SET costo_promedio = ?, ultima_actualizacion = datetime('now')
                    WHERE producto_id = ? AND sucursal_id = ?
                """, (costo_prom, prod_id, sucursal_id))

                # Sync productos.existencia (suma a través de sucursales) + precio_compra.
                self.db.execute("""
                    UPDATE productos
                    SET existencia   = (SELECT COALESCE(SUM(cantidad),0)
                                        FROM inventario_actual
                                        WHERE producto_id = ?),
                        precio_compra = ?
                    WHERE id = ?
                """, (prod_id, costo, prod_id))

            self.db.execute("""
                UPDATE trazabilidad_qr
                SET estado='recibido', fecha_recepcion=datetime('now'), recepcion_id=?
                WHERE uuid_qr=?
            """, (recepcion_id, uuid_qr))

            try:
                self.db.execute("""
                    UPDATE contenedores_qr
                    SET estado='disponible', sucursal_destino=?,
                        viaje_actual=viaje_actual+1, updated_at=datetime('now')
                    WHERE uuid_qr=?
                """, (sucursal_id, uuid_qr))
            except Exception as _e_cont:
                logger.warning("contenedores_qr update failed (non-fatal): %s", _e_cont)

        return recepcion_id

    # ── Asignación de contenedor ────────────────────────────────────────────────
    def guardar_asignacion(self, uuid_qr: str, proveedor_id, sucursal_id,
                           sucursal_destino, datos_extra: dict) -> None:
        self.db.execute("""
            INSERT INTO trazabilidad_qr
                (uuid_qr, tipo, proveedor_id, sucursal_id, sucursal_destino,
                 estado, datos_extra)
            VALUES(?,?,?,?,?,'asignado',?)
            ON CONFLICT(uuid_qr) DO UPDATE SET
                estado='asignado',
                proveedor_id=excluded.proveedor_id,
                sucursal_destino=excluded.sucursal_destino,
                datos_extra=excluded.datos_extra,
                fecha_generacion=datetime('now')
        """, (uuid_qr, "contenedor", proveedor_id,
              sucursal_id, sucursal_destino,
              json.dumps(datos_extra, ensure_ascii=False)))
        self.db.commit()

    def marcar_recepcion_parcial(self, uuid_qr: str) -> None:
        self.db.execute(
            "UPDATE trazabilidad_qr SET estado='recepcion_parcial' WHERE uuid_qr=?",
            (uuid_qr,)
        )
        self.db.commit()

    def marcar_incidencia(self, uuid_qr: str, incidencia_json: str) -> None:
        self.db.execute(
            "UPDATE trazabilidad_qr SET estado='incidencia', "
            "datos_extra=json_patch(COALESCE(datos_extra,'{}'), ?) WHERE uuid_qr=?",
            (f'{{"incidencia":{incidencia_json}}}', uuid_qr)
        )
        self.db.commit()
