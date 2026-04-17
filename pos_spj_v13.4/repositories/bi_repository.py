
# repositories/bi_repository.py
import logging

logger = logging.getLogger(__name__)

class BIRepository:
    """
    Capa de acceso a datos exclusiva para analítica pesada (Reportes BI).
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def get_kpis_generales(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str) -> dict:
        """Obtiene Total de Ventas, Ticket Promedio y Cantidad de Clientes."""
        query = """
            SELECT 
                COUNT(id) as total_tickets,
                SUM(total) as ingresos_totales,
                AVG(total) as ticket_promedio,
                COUNT(DISTINCT cliente_id) as clientes_unicos
            FROM ventas 
            WHERE sucursal_id = ? AND estado = 'completada'
            AND date(fecha) BETWEEN date(?) AND date(?)
        """
        row = self.db.execute(query, (sucursal_id, fecha_inicio, fecha_fin)).fetchone()
        return dict(row) if row else {'total_tickets': 0, 'ingresos_totales': 0, 'ticket_promedio': 0, 'clientes_unicos': 0}

    def get_ventas_por_hora(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str) -> list:
        """Agrupa las ventas según la hora del día para detectar 'Horas Pico'."""
        query = """
            SELECT 
                strftime('%H', fecha) as hora,
                COUNT(id) as cantidad_ventas,
                SUM(total) as ingresos
            FROM ventas
            WHERE sucursal_id = ? AND estado = 'completada'
            AND date(fecha) BETWEEN date(?) AND date(?)
            GROUP BY hora
            ORDER BY hora ASC
        """
        return [dict(row) for row in self.db.execute(query, (sucursal_id, fecha_inicio, fecha_fin)).fetchall()]

    def get_ranking_productos(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str, limite: int = 10, orden: str = 'DESC') -> list:
        """
        Obtiene los productos Más Vendidos (DESC) o los Lentos/Menos Vendidos (ASC).
        """
        query = f"""
            SELECT 
                p.nombre,
                SUM(d.cantidad) as cantidad_vendida,
                SUM(d.subtotal) as ingresos_generados
            FROM detalles_venta d
            JOIN ventas v ON d.venta_id = v.id
            JOIN productos p ON d.producto_id = p.id
            WHERE v.sucursal_id = ? AND v.estado = 'completada'
            AND date(v.fecha) BETWEEN date(?) AND date(?)
            GROUP BY p.id, p.nombre
            ORDER BY cantidad_vendida {orden}
            LIMIT ?
        """
        return [dict(row) for row in self.db.execute(query, (sucursal_id, fecha_inicio, fecha_fin, limite)).fetchall()]

    def get_clientes_recurrentes(self, sucursal_id: int, fecha_inicio: str, fecha_fin: str) -> list:
        """Identifica a los VIPs: Clientes que más veces han comprado y más han gastado."""
        query = """
            SELECT 
                c.nombre,
                COUNT(v.id) as visitas,
                SUM(v.total) as valor_vida
            FROM ventas v
            JOIN clientes c ON v.cliente_id = c.id
            WHERE v.sucursal_id = ? AND v.estado = 'completada' AND c.nombre != 'Público General'
            AND date(v.fecha) BETWEEN date(?) AND date(?)
            GROUP BY c.id, c.nombre
            ORDER BY valor_vida DESC
            LIMIT 10
        """
        return [dict(row) for row in self.db.execute(query, (sucursal_id, fecha_inicio, fecha_fin)).fetchall()]

    def get_ranking_cajeros(self, sucursal_id: int, fecha_inicio: str,
                            fecha_fin: str, limite: int = 20) -> list:
        """
        Ranking de cajeros por número de transacciones, volumen y ticket promedio.
        Fase 2 — Plan Maestro SPJ v13.4: frecuencia y rendimiento por cajero.
        """
        query = """
            SELECT
                COALESCE(usuario, '(sin usuario)') AS cajero,
                COUNT(id)          AS num_ventas,
                SUM(total)         AS total_ventas,
                AVG(total)         AS ticket_promedio,
                SUM(descuento)     AS total_descuentos,
                COUNT(DISTINCT DATE(fecha)) AS dias_activo
            FROM ventas
            WHERE sucursal_id = ?
              AND estado = 'completada'
              AND date(fecha) BETWEEN date(?) AND date(?)
            GROUP BY usuario
            ORDER BY num_ventas DESC
            LIMIT ?
        """
        return [dict(row) for row in self.db.execute(
            query, (sucursal_id, fecha_inicio, fecha_fin, limite)).fetchall()]

    def get_scan_telemetria(self, sucursal_id: int, fecha_inicio: str,
                            fecha_fin: str) -> list:
        """
        Resumen de eventos de escaneo por tipo y acción.
        Fase 2 — trazabilidad de escáner.
        """
        try:
            query = """
                SELECT tipo, accion, COUNT(*) AS total
                FROM scan_event_log
                WHERE sucursal_id = ?
                  AND date(created_at) BETWEEN date(?) AND date(?)
                GROUP BY tipo, accion
                ORDER BY total DESC
            """
            return [dict(row) for row in self.db.execute(
                query, (sucursal_id, fecha_inicio, fecha_fin)).fetchall()]
        except Exception:
            return []