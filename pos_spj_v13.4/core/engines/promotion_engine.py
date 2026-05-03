
# core/engines/promotion_engine.py
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class PromotionEngine:
    """
    Motor matemático para cálculo de Promociones.
    Diseñado con un 'Guardrail' (Muro de contención) anti-pérdidas.
    """
    
    def __init__(self, margen_seguridad_minimo: float = 0.05):
        # Por defecto, el precio final NUNCA puede ser menor al costo + 5%
        self.margen_minimo = margen_seguridad_minimo

    def aplicar_promociones(self, carrito: List[Dict], promociones_activas: List[Dict], contexto: Dict) -> Dict:
        """
        Toma el carrito original, evalúa las reglas y devuelve el carrito con descuentos aplicados,
        garantizando matemáticamente que ningún producto se venda a pérdida.
        """
        # Normalizar claves — la UI puede enviar unit_price/qty o precio_unitario/cantidad
        def _precio(item):
            return float(item.get('precio_unitario', item.get('unit_price', item.get('precio', 0))))

        def _cantidad(item):
            return float(item.get('cantidad', item.get('qty', 1)))

        def _nombre(item):
            return item.get('nombre', item.get('name', ''))

        # Normalizar todos los ítems antes de procesar
        carrito_calculado = []
        for item in carrito:
            norm = item.copy()
            norm['precio_unitario'] = _precio(item)
            norm['cantidad']        = _cantidad(item)
            norm['nombre']          = _nombre(item)
            norm.setdefault('id', item.get('product_id', item.get('id', 0)))
            carrito_calculado.append(norm)
        descuento_total = 0.0
        
        # Extraemos el contexto de la venta
        hora_actual = contexto.get('hora_actual', datetime.now().time())
        dia_actual = contexto.get('dia_semana', datetime.now().weekday())
        nivel_cliente = contexto.get('nivel_cliente', 'regular')

        # Filtramos las promociones que aplican en este momento exacto
        promos_validas = self._filtrar_promociones_validas(promociones_activas, hora_actual, dia_actual, nivel_cliente)

        # Ordenamos las promociones por prioridad (Ej. Los Combos se calculan antes que los % de descuento)
        promos_validas.sort(key=lambda x: x.get('prioridad', 99))

        for promo in promos_validas:
            for item in carrito_calculado:
                
                # Evitar aplicar descuento sobre algo que ya es parte de otra promoción (Evita apilar descuentos)
                if item.get('promocion_aplicada'):
                    continue

                descuento_item = 0.0

                # 1. REGLA: Descuento por Porcentaje (Ej. 10% en Pechuga)
                if promo['tipo'] == 'porcentaje' and self._aplica_a_item(promo, item):
                    descuento_item = item['precio_unitario'] * (promo['valor'] / 100.0)

                # 2. REGLA: 2x1 (BOGO - Buy One Get One)
                elif promo['tipo'] == '2x1' and self._aplica_a_item(promo, item):
                    cantidad = int(item['cantidad'])
                    # Si lleva 3, solo se descuenta 1. Si lleva 4, se descuentan 2.
                    items_gratis = cantidad // 2 
                    # El descuento se prorratea por unidad para la contabilidad
                    descuento_item = (items_gratis * item['precio_unitario']) / cantidad if cantidad > 0 else 0

                # --- 🛡️ EL MURO ANTI-PÉRDIDAS (LA GARANTÍA MATEMÁTICA) ---
                if descuento_item > 0:
                    costo_seguro = item.get('costo_unitario', 0.0) * (1 + self.margen_minimo)
                    precio_propuesto = item['precio_unitario'] - descuento_item
                    
                    if precio_propuesto < costo_seguro:
                        logger.warning(f"Protección anti-pérdidas activada en {item['nombre']}. Precio propuesto: {precio_propuesto}, Costo Seguro: {costo_seguro}")
                        # Topamos el descuento para que el precio final sea exactamente el costo seguro
                        descuento_item = item['precio_unitario'] - costo_seguro
                        precio_propuesto = costo_seguro

                    # Aplicamos el descuento final al item
                    item['descuento_unitario'] = descuento_item
                    item['precio_final'] = precio_propuesto
                    item['subtotal'] = precio_propuesto * item['cantidad']
                    item['promocion_aplicada'] = promo['nombre']
                    
                    descuento_total += (descuento_item * item['cantidad'])

        # Recalcular el total del carrito
        total_final = sum(item.get('subtotal', item['precio_unitario'] * _cantidad(item)) for item in carrito_calculado)

        return {
            "carrito_descontado": carrito_calculado,
            "descuento_total_aplicado": descuento_total,
            "gran_total": total_final
        }

    def _filtrar_promociones_validas(self, promociones: List[Dict], hora, dia, nivel_cliente) -> List[Dict]:
        validas = []
        for p in promociones:
            # Validar Horario (Happy Hour)
            if 'hora_inicio' in p and 'hora_fin' in p:
                if not (p['hora_inicio'] <= hora <= p['hora_fin']): continue
            
            # Validar Nivel de Cliente (Fidelidad)
            if 'nivel_cliente_requerido' in p:
                if p['nivel_cliente_requerido'] != nivel_cliente and p['nivel_cliente_requerido'] != 'todos': continue
                
            validas.append(p)
        return validas

    def _aplica_a_item(self, promo: Dict, item: Dict) -> bool:
        """Determina si la promoción aplica a este producto específico o a su categoría."""
        if promo.get('aplica_a') == 'producto_id' and item.get('id', item.get('product_id', 0)) == promo['target_id']:
            return True
        if promo.get('aplica_a') == 'categoria' and item.get('categoria') == promo['target_id']:
            return True
        return False