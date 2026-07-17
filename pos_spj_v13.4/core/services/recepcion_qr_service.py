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

logger = logging.getLogger("spj.services.recepcion_qr")


class RecepcionQRService:
    def __init__(self, db):
        self.db = db

    # NOTA (PUR-13): `procesar_recepcion` (escritura directa de inventario) fue
    # eliminada. La recepción QR canónica vive en CompleteQrReceptionUseCase
    # (backend/application/procurement) → GoodsReceipt + entrada de stock por
    # evento (PurchaseStockEntryHandler). Este servicio conserva sólo lecturas y
    # utilidades de trazabilidad.

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

    def registrar_contenedor(self, uuid_qr: str, codigo_interno, descripcion,
                             sucursal_origen) -> None:
        """Registra (o ignora si ya existe) un contenedor recién generado."""
        self.db.execute("""
            INSERT OR IGNORE INTO contenedores_qr
                (uuid_qr, codigo_interno, descripcion, sucursal_origen)
            VALUES(?,?,?,?)
        """, (uuid_qr, codigo_interno, descripcion, sucursal_origen))
        self.db.commit()

    # ── Lecturas (consultas para la UI) ─────────────────────────────────────────
    # Preservan EXACTAMENTE el SQL que vivía embebido en RecepcionQRWidget y
    # devuelven las filas crudas (self.db mantiene su row_factory), de modo que el
    # indexado/columnas aguas abajo en el widget no cambian.

    def listar_pos_abiertas(self) -> list:
        return self.db.execute(
            "SELECT id, folio, proveedor_nombre, estado FROM ordenes_compra "
            "WHERE estado IN ('ABIERTA','PARCIAL','borrador','pendiente') "
            "ORDER BY id DESC LIMIT 100"
        ).fetchall()

    def listar_contenedores_disponibles(self) -> list:
        return self.db.execute("""
            SELECT c.uuid_qr,
                   COALESCE(c.codigo_interno, '') as codigo,
                   COALESCE(c.descripcion, '') as desc,
                   COALESCE(t.estado, 'disponible') as estado
            FROM contenedores_qr c
            LEFT JOIN trazabilidad_qr t ON t.uuid_qr = c.uuid_qr
            WHERE COALESCE(t.estado, 'disponible') IN ('disponible','generado')
            ORDER BY c.created_at DESC LIMIT 100
        """).fetchall()

    def listar_pendientes_recepcion(self) -> list:
        return self.db.execute("""
            SELECT t.uuid_qr,
                   COALESCE(c.codigo_interno, t.uuid_qr) AS codigo,
                   t.estado,
                   COALESCE(p.nombre, '—') AS proveedor
            FROM trazabilidad_qr t
            LEFT JOIN contenedores_qr c ON c.uuid_qr = t.uuid_qr
            LEFT JOIN proveedores p ON p.id = (
                SELECT json_extract(t2.datos_extra,'$.proveedor_id')
                FROM trazabilidad_qr t2 WHERE t2.uuid_qr = t.uuid_qr LIMIT 1
            )
            WHERE t.estado IN ('asignado','en_transito','enviado')
            ORDER BY t.fecha_generacion DESC LIMIT 50
        """).fetchall()

    def listar_proveedores_activos(self) -> list:
        return self.db.execute(
            "SELECT id, nombre FROM proveedores WHERE activo=1 ORDER BY nombre LIMIT 200"
        ).fetchall()

    def historial_qr(self, desde: str, hasta: str) -> list:
        return self.db.execute("""
            SELECT COALESCE(c.codigo_interno, t.uuid_qr) AS contenedor,
                   COALESCE(json_extract(t.datos_extra,'$.tipo_contenedor'), 'Caja') AS tipo,
                   COALESCE(p.nombre,'—') AS proveedor,
                   COALESCE(json_extract(t.datos_extra,'$.factura'),'—') AS factura,
                   COALESCE(s.nombre,'—') AS sucursal_destino,
                   COALESCE(t.estado,'—') AS estado,
                   COALESCE(CAST(json_extract(t.datos_extra,'$.peso_estimado') AS REAL),0) AS peso_est,
                   COALESCE(r.peso_total_kg,0) AS peso_rec,
                   COALESCE(CAST(json_extract(t.datos_extra,'$.monto_total') AS REAL),0) AS total,
                   COALESCE(r.created_at,'—') AS fecha_recepcion,
                   t.uuid_qr
            FROM trazabilidad_qr t
            LEFT JOIN contenedores_qr c ON c.uuid_qr = t.uuid_qr
            LEFT JOIN proveedores p ON p.id = CAST(json_extract(t.datos_extra,'$.proveedor_id') AS INTEGER)
            LEFT JOIN sucursales s ON s.id = t.sucursal_destino
            LEFT JOIN recepciones r ON r.uuid_qr = t.uuid_qr AND r.estado='completada'
            WHERE DATE(COALESCE(r.created_at, t.fecha_generacion)) BETWEEN ? AND ?
            ORDER BY COALESCE(r.created_at, t.fecha_generacion) DESC LIMIT 300
        """, (desde, hasta)).fetchall()

    def detalle_contenedor(self, uuid_qr: str):
        return self.db.execute(
            "SELECT uuid_qr, COALESCE(codigo_interno,'—'), COALESCE(descripcion,'—') FROM contenedores_qr WHERE uuid_qr=?",
            (uuid_qr,)
        ).fetchone()

    def timeline_movimientos(self, uuid_qr: str) -> list:
        like = f"%{uuid_qr[:8]}%"
        return self.db.execute("""
            SELECT fecha, tipo_movimiento, usuario FROM movimientos_inventario
            WHERE referencia LIKE ? OR descripcion LIKE ?
            ORDER BY fecha DESC LIMIT 10
        """, (like, like)).fetchall()

    def obtener_trazabilidad(self, uuid_qr: str):
        return self.db.execute(
            "SELECT * FROM trazabilidad_qr WHERE uuid_qr=? LIMIT 1", (uuid_qr,)
        ).fetchone()

    def obtener_trazabilidad_con_proveedor(self, uuid_qr: str):
        return self.db.execute("""
            SELECT t.*, p.nombre as proveedor_nombre
            FROM trazabilidad_qr t
            LEFT JOIN proveedores p ON p.id = t.proveedor_id
            WHERE t.uuid_qr=? LIMIT 1""", (uuid_qr,)
        ).fetchone()

    def buscar_proveedores(self, texto: str) -> list:
        return self.db.execute(
            "SELECT id, nombre, rfc FROM proveedores WHERE activo=1 "
            "AND (nombre LIKE ? OR rfc LIKE ?) ORDER BY nombre LIMIT 8",
            (f"%{texto}%", f"%{texto}%")
        ).fetchall()

    def buscar_productos(self, texto: str) -> list:
        return self.db.execute(
            """SELECT id, nombre, COALESCE(codigo,'') as codigo,
                      COALESCE(precio_compra,0) as costo,
                      COALESCE(unidad,'pz') as unidad
               FROM productos
               WHERE (nombre LIKE ? OR COALESCE(codigo,'') LIKE ?
                      OR COALESCE(codigo_barras,'') LIKE ?
                      OR CAST(id AS TEXT) = ?)
                 AND COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1
               ORDER BY nombre LIMIT 10""",
            (f"%{texto}%", f"%{texto}%", f"%{texto}%", texto)
        ).fetchall()

    def listar_sucursales_activas(self) -> list:
        return self.db.execute(
            "SELECT id, nombre FROM sucursales WHERE activa=1 AND id IS NOT NULL AND TRIM(id) != '' AND LOWER(TRIM(id)) NOT IN ('none','null') ORDER BY nombre"
        ).fetchall()

    def historial_recepciones(self, sucursal_id) -> list:
        return self.db.execute("""
            SELECT r.folio, r.created_at, p.nombre as proveedor,
                   r.condicion_pago, r.monto_total, r.monto_pagado,
                   r.estado
            FROM recepciones r
            LEFT JOIN proveedores p ON p.id = r.proveedor_id
            WHERE r.sucursal_id = ? AND r.tipo='COMPRA'
            ORDER BY r.created_at DESC LIMIT 100
        """, (sucursal_id,)).fetchall()
