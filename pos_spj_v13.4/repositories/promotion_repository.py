
# repositories/promotion_repository.py
import logging

logger = logging.getLogger(__name__)

class PromotionRepository:
    """
    Capa de acceso a datos para las reglas de Promociones y Descuentos.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def get_active_promotions(self, branch_id: int) -> list:
        """
        Obtiene todas las promociones activas para una sucursal específica.
        """
        query = """
            SELECT 
                id, nombre, tipo, valor, aplica_a, target_id, 
                hora_inicio, hora_fin, nivel_cliente_requerido, prioridad
            FROM promociones
            WHERE activa = 1 
            AND (sucursal_id = ? OR sucursal_id = 0) -- 0 significa 'Todas las sucursales'
            AND fecha_inicio <= date('now') 
            AND fecha_fin >= date('now')
            ORDER BY prioridad ASC
        """
        try:
            rows = self.db.execute(query, (branch_id,)).fetchall()
            promociones = []
            for row in rows:
                promo = dict(row)
                # Convertir horas de texto a objetos time de Python si existen
                if promo['hora_inicio']:
                    from datetime import datetime
                    promo['hora_inicio'] = datetime.strptime(promo['hora_inicio'], '%H:%M:%S').time()
                if promo['hora_fin']:
                    from datetime import datetime
                    promo['hora_fin'] = datetime.strptime(promo['hora_fin'], '%H:%M:%S').time()
                
                promociones.append(promo)
            return promociones
            
        except Exception as e:
            logger.error(f"Error consultando promociones activas para sucursal {branch_id}: {str(e)}")
            return []