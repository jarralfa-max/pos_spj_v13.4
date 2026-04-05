
# core/services/bi_service.py
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class BIService:
    """
    Orquestador de Inteligencia de Negocios.
    Recopila los datos de los repositorios y los formatea para el Dashboard.
    """
    def __init__(self, bi_repo, feature_flag_service):
        self.repo = bi_repo
        self.feature_flag_service = feature_flag_service

    # ── Caché en memoria: evita recalcular el mismo rango repetidamente ─────
    _cache: dict = {}
    _cache_ts: dict = {}
    CACHE_TTL_SECONDS = 60   # datos de 'hoy' se refrescan cada 60s tras una venta

    def get_dashboard_data(self, branch_id: int, rango: str = 'hoy') -> dict:
        """
        Construye el paquete completo de datos para el Dashboard.
        Cache strategy:
          - 'hoy'   → usa ventas_diarias (agregados) + caché 60s en memoria
          - 'semana'/'mes' → caché 5 min (datos históricos no cambian frecuente)
        """
        import time
        # Intentar validar feature flag sin lanzar excepción
        try:
            self.feature_flag_service.require_feature('bi_v2', branch_id)
        except Exception:
            pass  # Si el flag no existe, continuar igual

        # ── Caché en memoria ──────────────────────────────────────────────
        cache_key = f"{branch_id}:{rango}"
        ttl = 60 if rango == 'hoy' else 300
        now = time.monotonic()
        if cache_key in self._cache:
            if now - self._cache_ts.get(cache_key, 0) < ttl:
                logger.debug("BI cache HIT: %s", cache_key)
                return self._cache[cache_key]

        # ── Calcular fechas ───────────────────────────────────────────────
        hoy = datetime.now()
        if rango == 'hoy':
            fecha_inicio = fecha_fin = hoy.strftime('%Y-%m-%d')
        elif rango == 'semana':
            fecha_inicio = (hoy - timedelta(days=hoy.weekday())).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
        elif rango == 'mes':
            fecha_inicio = hoy.replace(day=1).strftime('%Y-%m-%d')
            fecha_fin = hoy.strftime('%Y-%m-%d')
        else:
            fecha_inicio = fecha_fin = hoy.strftime('%Y-%m-%d')

        # ── Intentar leer desde ventas_diarias (tabla de agregados) ──────
        # Mucho más rápido que recalcular desde detalles_venta
        try:
            if rango == 'hoy':
                row = self.repo.db.execute("""
                    SELECT COALESCE(SUM(total_ventas),0),
                           COALESCE(SUM(num_transacciones),0),
                           COALESCE(AVG(ticket_promedio),0),
                           COALESCE(SUM(clientes_nuevos),0)
                    FROM ventas_diarias
                    WHERE fecha=? AND sucursal_id=?
                """, (fecha_inicio, branch_id)).fetchone()
                if row and float(row[0]) > 0:
                    # Datos del día ya agregados → respuesta instantánea
                    kpis_fast = {
                        'ingresos_totales': float(row[0]),
                        'total_tickets':    int(row[1]),
                        'ticket_promedio':  float(row[2]),
                        'clientes_unicos':  int(row[3]),
                    }
                    dashboard = {
                        'periodo':            f"{fecha_inicio} al {fecha_fin}",
                        'fuente':             'ventas_diarias',
                        'kpis': {
                            'ingresos':         kpis_fast['ingresos_totales'],
                            'tickets':          kpis_fast['total_tickets'],
                            'ticket_promedio':  kpis_fast['ticket_promedio'],
                            'clientes_unicos':  kpis_fast['clientes_unicos'],
                        },
                        'ventas_por_hora':      self.repo.get_ventas_por_hora(
                            branch_id, fecha_inicio, fecha_fin),
                        'top_productos':        self.repo.get_ranking_productos(
                            branch_id, fecha_inicio, fecha_fin, limite=5, orden='DESC'),
                        'productos_lentos':     self.repo.get_ranking_productos(
                            branch_id, fecha_inicio, fecha_fin, limite=5, orden='ASC'),
                        'clientes_recurrentes': self.repo.get_clientes_recurrentes(
                            branch_id, fecha_inicio, fecha_fin),
                    }
                    self._cache[cache_key] = dashboard
                    self._cache_ts[cache_key] = now
                    logger.debug("BI desde ventas_diarias: %s", cache_key)
                    return dashboard
        except Exception as e:
            logger.debug("ventas_diarias no disponible, calculando en tiempo real: %s", e)

        # ── Fallback: calcular desde ventas (tiempo real) ─────────────────
        try:
            kpis = self.repo.get_kpis_generales(branch_id, fecha_inicio, fecha_fin)
            dashboard = {
                'periodo': f"{fecha_inicio} al {fecha_fin}",
                'fuente':  'tiempo_real',
                'kpis': {
                    'ingresos':         kpis.get('ingresos_totales') or 0.0,
                    'tickets':          kpis.get('total_tickets') or 0,
                    'ticket_promedio':  kpis.get('ticket_promedio') or 0.0,
                    'clientes_unicos':  kpis.get('clientes_unicos') or 0,
                },
                'ventas_por_hora':      self.repo.get_ventas_por_hora(
                    branch_id, fecha_inicio, fecha_fin),
                'top_productos':        self.repo.get_ranking_productos(
                    branch_id, fecha_inicio, fecha_fin, limite=5, orden='DESC'),
                'productos_lentos':     self.repo.get_ranking_productos(
                    branch_id, fecha_inicio, fecha_fin, limite=5, orden='ASC'),
                'clientes_recurrentes': self.repo.get_clientes_recurrentes(
                    branch_id, fecha_inicio, fecha_fin),
            }
            # Comparativa vs período anterior
            try:
                dashboard['comparativa'] = self._get_comparativa(branch_id, rango)
            except Exception:
                dashboard['comparativa'] = {}

            self._cache[cache_key] = dashboard
            self._cache_ts[cache_key] = now
            return dashboard
        except Exception as e:
            logger.error("Fallo al generar Dashboard BI para sucursal %d: %s", branch_id, e)
            raise RuntimeError("No se pudo generar el reporte analítico.")

    def _get_comparativa(self, sucursal_id: int, rango: str) -> dict:
        """KPIs del período anterior: hoy→ayer, semana→semana pasada, mes→mes pasado."""
        from datetime import date, timedelta
        hoy = date.today()
        if rango == 'hoy':
            fi = ff = (hoy - timedelta(days=1)).isoformat()
        elif rango == 'semana':
            ff = (hoy - timedelta(days=7)).isoformat()
            fi = (hoy - timedelta(days=14)).isoformat()
        else:
            ff = (hoy - timedelta(days=30)).isoformat()
            fi = (hoy - timedelta(days=60)).isoformat()
        kpis = self.repo.get_kpis_generales(sucursal_id, fi, ff)
        return {
            'ingresos':    float(kpis.get('ingresos_totales') or 0),
            'num_ventas':  int(kpis.get('total_tickets') or 0),
            'ticket_prom': float(kpis.get('ticket_promedio') or 0),
            'periodo':     f"{fi} → {ff}",
        }

    def invalidar_cache(self, branch_id: int = None) -> None:
        """Invalida el caché tras una venta (llamado desde EventBus)."""
        if branch_id:
            key = f"{branch_id}:hoy"
            self._cache.pop(key, None)
            self._cache_ts.pop(key, None)
        else:
            self._cache.clear()
            self._cache_ts.clear()