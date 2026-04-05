
# core/services/forecast_service.py
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except ImportError:
    ExponentialSmoothing = None

logger = logging.getLogger(__name__)

class ForecastService:
    """
    Motor de Inteligencia Artificial para Pronóstico de Demanda.
    Utiliza suavizado exponencial (Holt-Winters) y cálculo de inventario.
    """
    def __init__(self, db_conn):
        self.db = db_conn

    def generar_plan_compras(self, producto_id: int, sucursal_id: int, dias_historial: int, dias_pronostico: int, stock_seguridad: float) -> dict:
        """
        Analiza el pasado para predecir el futuro y calcular cuánto comprar hoy.
        """
        if not ExponentialSmoothing:
            raise RuntimeError("La librería 'statsmodels' no está instalada en el servidor.")

        # 1. Extraer historial de ventas (El repositorio integrado)
        query_historial = """
            SELECT date(v.fecha) as fecha, SUM(d.cantidad) as total_vendido
            FROM ventas v
            JOIN detalles_venta d ON v.id = d.venta_id
            WHERE d.producto_id = ? 
              AND v.sucursal_id = ? 
              AND v.estado = 'completada'
              AND v.fecha >= date('now', ?)
            GROUP BY date(v.fecha)
            ORDER BY date(v.fecha) ASC
        """
        # Formatear el modificador de fecha (ej. '-30 days')
        modificador_fecha = f"-{dias_historial} days"
        
        df = pd.read_sql_query(
            query_historial, 
            self.db, 
            params=(producto_id, sucursal_id, modificador_fecha),
            parse_dates=['fecha']
        )

        if df.empty or len(df) < 3:
            raise ValueError(f"No hay suficientes datos históricos (mínimo 3 días) para pronosticar este producto.")

        # 2. Preparar el DataFrame (Rellenar días sin ventas con 0)
        df.set_index('fecha', inplace=True)
        # Crear un rango de fechas completo para evitar huecos en la serie de tiempo
        idx = pd.date_range(start=df.index.min(), end=df.index.max(), freq='D')
        df = df.reindex(idx, fill_value=0.0)

        # 3. ENTRENAR EL MODELO DE IA (Holt-Winters)
        # Usamos tendencia aditiva. Si hubiera suficiente data, podríamos usar 'seasonal'
        modelo = ExponentialSmoothing(df['total_vendido'], trend='add', seasonal=None, initialization_method="estimated")
        modelo_ajustado = modelo.fit()

        # 4. Generar Pronóstico Futuro
        predicciones = modelo_ajustado.forecast(steps=dias_pronostico)
        # Evitar predicciones negativas (no puedes vender -5 pollos)
        predicciones = predicciones.apply(lambda x: max(0.0, x))
        
        total_proyectado = predicciones.sum()

        # 5. Calcular la Compra Recomendada
        cursor = self.db.cursor()
        stock_actual_row = cursor.execute("SELECT existencia FROM productos WHERE id = ?", (producto_id,)).fetchone()
        stock_actual = stock_actual_row['existencia'] if stock_actual_row else 0.0

        # Fórmula Maestra: (Lo que voy a vender) - (Lo que ya tengo) + (Mi colchón de seguridad)
        cantidad_a_comprar = max(0.0, (total_proyectado - stock_actual) + stock_seguridad)

        # 6. Empaquetar resultados para la UI
        fechas_futuras = [ (datetime.now() + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(1, dias_pronostico + 1) ]

        return {
            "historial_fechas": [d.strftime('%Y-%m-%d') for d in df.index],
            "historial_valores": df['total_vendido'].tolist(),
            "pronostico_fechas": fechas_futuras,
            "pronostico_valores": predicciones.tolist(),
            "metricas": {
                "stock_actual": stock_actual,
                "venta_proyectada": total_proyectado,
                "compra_recomendada": cantidad_a_comprar
            }
        }