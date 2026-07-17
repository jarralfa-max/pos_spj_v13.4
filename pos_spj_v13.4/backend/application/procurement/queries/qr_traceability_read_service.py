"""Read services for the QR-container lifecycle (migrated from the legacy monolith
+ RecepcionQRService reads). Paginated, no business logic; tolerate missing
tables on a fresh dev DB.
"""

from __future__ import annotations

import sqlite3
from typing import Any


class _Base:
    def __init__(self, connection: Any) -> None:
        self._conn = connection

    def _rows(self, sql: str, params: tuple = ()) -> list[dict]:
        try:
            cur = self._conn.execute(sql, params)
        except sqlite3.OperationalError:
            return []
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._rows(sql, params)
        return rows[0] if rows else None


class QrTraceabilityReadService(_Base):
    def available_containers(self, *, limit: int = 100) -> list[dict]:
        return self._rows(
            "SELECT c.uuid_qr, COALESCE(c.codigo_interno,'') AS code,"
            " COALESCE(c.descripcion,'') AS description,"
            " COALESCE(t.estado,'disponible') AS status"
            " FROM contenedores_qr c LEFT JOIN trazabilidad_qr t ON t.uuid_qr=c.uuid_qr"
            " WHERE COALESCE(t.estado,'disponible') IN ('disponible','generado')"
            " ORDER BY c.created_at DESC LIMIT ?", (int(limit),))

    def pending_reception(self, *, limit: int = 50) -> list[dict]:
        return self._rows(
            "SELECT t.uuid_qr, COALESCE(c.codigo_interno, t.uuid_qr) AS code, t.estado AS status,"
            " COALESCE(p.nombre,'—') AS supplier"
            " FROM trazabilidad_qr t"
            " LEFT JOIN contenedores_qr c ON c.uuid_qr=t.uuid_qr"
            " LEFT JOIN proveedores p ON p.id=("
            "   SELECT json_extract(t2.datos_extra,'$.proveedor_id')"
            "   FROM trazabilidad_qr t2 WHERE t2.uuid_qr=t.uuid_qr LIMIT 1)"
            " WHERE t.estado IN ('asignado','en_transito','enviado')"
            " ORDER BY t.fecha_generacion DESC LIMIT ?", (int(limit),))

    def history(self, desde: str, hasta: str, *, limit: int = 300) -> list[dict]:
        return self._rows(
            "SELECT COALESCE(c.codigo_interno, t.uuid_qr) AS container,"
            " COALESCE(p.nombre,'—') AS supplier,"
            " COALESCE(s.nombre,'—') AS destination,"
            " COALESCE(t.estado,'—') AS status,"
            " COALESCE(r.created_at,'—') AS received_at, t.uuid_qr"
            " FROM trazabilidad_qr t"
            " LEFT JOIN contenedores_qr c ON c.uuid_qr=t.uuid_qr"
            " LEFT JOIN proveedores p ON p.id=CAST(json_extract(t.datos_extra,'$.proveedor_id') AS TEXT)"
            " LEFT JOIN sucursales s ON s.id=t.sucursal_destino"
            " LEFT JOIN recepciones r ON r.uuid_qr=t.uuid_qr AND r.estado='completada'"
            " WHERE DATE(COALESCE(r.created_at, t.fecha_generacion)) BETWEEN ? AND ?"
            " ORDER BY COALESCE(r.created_at, t.fecha_generacion) DESC LIMIT ?",
            (desde, hasta, int(limit)))

    def container_detail(self, uuid_qr: str) -> dict | None:
        return self._one(
            "SELECT uuid_qr, COALESCE(codigo_interno,'—') AS code,"
            " COALESCE(descripcion,'—') AS description FROM contenedores_qr WHERE uuid_qr=?",
            (uuid_qr,))

    def search_suppliers(self, text: str, *, limit: int = 8) -> list[dict]:
        like = f"%{text}%"
        return self._rows(
            "SELECT id, nombre AS name, COALESCE(rfc,'') AS rfc FROM proveedores"
            " WHERE COALESCE(activo,1)=1 AND (nombre LIKE ? OR rfc LIKE ?)"
            " ORDER BY nombre LIMIT ?", (like, like, int(limit)))

    def search_products(self, text: str, *, limit: int = 10) -> list[dict]:
        like = f"%{text}%"
        return self._rows(
            "SELECT id, nombre AS name, COALESCE(codigo,'') AS code,"
            " COALESCE(precio_compra,0) AS cost, COALESCE(unidad,'pz') AS unit"
            " FROM productos WHERE (nombre LIKE ? OR COALESCE(codigo,'') LIKE ?"
            "   OR COALESCE(codigo_barras,'') LIKE ? OR CAST(id AS TEXT)=?)"
            " AND COALESCE(oculto,0)=0 AND COALESCE(activo,1)=1"
            " ORDER BY nombre LIMIT ?", (like, like, like, text, int(limit)))
