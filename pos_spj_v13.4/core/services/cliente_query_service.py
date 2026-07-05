# core/services/cliente_query_service.py
"""
ClienteQueryService — lecturas de clientes/tarjetas/fidelidad para la UI.

Ruta canónica: los diálogos de clientes NO ejecutan SQL; delegan sus lecturas
aquí (Remediación D). Cada método preserva exactamente la consulta que antes
vivía embebida en el diálogo.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("spj.services.cliente_query")


class ClienteQueryService:
    def __init__(self, db):
        self.db = db

    # ── Historial del cliente (DialogoHistorialCliente) ─────────────────────────
    def historial_compras(self, id_cliente) -> list:
        return self.db.execute(
            "SELECT fecha, total, metodo_pago, puntos_ganados "
            "FROM ventas WHERE cliente_id = ? ORDER BY fecha DESC",
            (id_cliente,)
        ).fetchall()

    def historial_puntos(self, id_cliente) -> list:
        return self.db.execute(
            "SELECT fecha, tipo, puntos, saldo_actual, descripcion "
            "FROM historico_puntos WHERE id_cliente = ? ORDER BY fecha DESC",
            (id_cliente,)
        ).fetchall()

    def historial_creditos(self, id_cliente) -> list:
        return self.db.execute(
            "SELECT fecha, tipo, monto, descripcion, usuario "
            "FROM movimientos_credito WHERE cliente_id = ? ORDER BY fecha DESC",
            (id_cliente,)
        ).fetchall()

    # ── Tarjetas (asignar / gestionar) ──────────────────────────────────────────
    def tarjetas_libres(self, limit: int = 100) -> list:
        return self.db.execute(
            "SELECT id, numero, COALESCE(nivel,'Bronce') FROM tarjetas_fidelidad "
            "WHERE estado IN ('libre','impresa','generada') ORDER BY id LIMIT ?",
            (limit,)
        ).fetchall()

    def buscar_tarjeta(self, numero: str):
        return self.db.execute(
            "SELECT id, numero, estado FROM tarjetas_fidelidad WHERE numero=? OR codigo_qr=?",
            (numero, numero)
        ).fetchone()

    def tarjetas_de_cliente(self, cliente_id) -> list:
        return self.db.execute(
            "SELECT id, numero, estado, COALESCE(nivel,'Bronce'), puntos_actuales, fecha_asignacion "
            "FROM tarjetas_fidelidad WHERE id_cliente = ? ORDER BY fecha_asignacion DESC",
            (cliente_id,)
        ).fetchall()

    def historial_asignaciones(self, cliente_id, limit: int = 100) -> list:
        return self.db.execute(
            """
            SELECT h.accion, h.fecha, tf.numero, h.motivo, h.usuario
            FROM card_assignment_history h
            LEFT JOIN tarjetas_fidelidad tf ON tf.id = h.tarjeta_id
            WHERE h.cliente_id_nuevo = ? OR h.cliente_id_prev = ?
            ORDER BY h.fecha DESC LIMIT ?
            """,
            (cliente_id, cliente_id, limit)
        ).fetchall()

    def loyalty_score(self, cliente_id):
        return self.db.execute(
            "SELECT score_total, nivel, visitas_periodo, importe_total, "
            "margen_generado, referidos, fecha_calculo "
            "FROM loyalty_scores WHERE cliente_id = ?",
            (cliente_id,)
        ).fetchone()

    # ── Segmentación RFM (_DialogoRFM) ──────────────────────────────────────────
    def rfm_ventas(self, dias: int, limit: int = 500) -> list:
        """Agregado de ventas por cliente en la ventana `dias` para el análisis RFM.
        Parametriza el modificador de fecha (antes interpolado en un f-string)."""
        return self.db.execute(
            "SELECT c.id, c.nombre, c.telefono, "
            "       MAX(v.fecha) AS ultima_compra, "
            "       COUNT(v.id)  AS num_compras, "
            "       SUM(v.total) AS total_gastado "
            "FROM clientes c "
            "JOIN ventas v ON v.cliente_id = c.id "
            "WHERE v.estado = 'completada' AND v.fecha >= date('now', ?) "
            "GROUP BY c.id "
            "ORDER BY total_gastado DESC LIMIT ?",
            (f"-{int(dias)} days", limit)
        ).fetchall()
