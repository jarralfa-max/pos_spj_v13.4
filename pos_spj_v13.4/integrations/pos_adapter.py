
import sqlite3
import logging
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple
import os
import sys

# Agregar path para imports del sistema existente
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from database.conexion import get_db_connection

# Configurar logging
logger = logging.getLogger(__name__)

class POSAdapter:
    """Adaptador para conectar el servicio de WhatsApp con el sistema POS existente"""
    
    def __init__(self):
        pass  # Usaremos get_db_connection directamente
    
    def _get_connection(self):
        """Obtener conexión a la base de datos usando el sistema existente"""
        return get_db_connection()
    
    def buscar_producto(self, nombre: str) -> Optional[Dict]:
        """
        Buscar producto por nombre usando la estructura existente
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Adaptado a tu estructura de productos
            cursor.execute('''
                SELECT id, nombre, precio, existencia, categoria 
                FROM productos 
                WHERE nombre LIKE ? AND oculto = 0
                ORDER BY 
                    CASE WHEN nombre = ? THEN 1 
                         WHEN nombre LIKE ? THEN 2 
                         ELSE 3 END
                LIMIT 1
            ''', (f'%{nombre}%', nombre, f'{nombre}%'))
            
            resultado = cursor.fetchone()
            if resultado:
                return {
                    'id': resultado[0],
                    'nombre': resultado[1],
                    'precio_venta': float(resultado[2]),
                    'stock': float(resultado[3]),
                    'categoria': resultado[4]
                }
            return None
        except Exception as e:
            logger.error(f"Error buscando producto {nombre}: {e}")
            return None
        finally:
            if 'conn' in locals():
                conn.close()
    
    def verificar_inventario(self, producto_id: int, cantidad: float) -> Tuple[bool, float]:
        """
        Verificar si hay suficiente inventario para un producto
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT existencia FROM productos WHERE id = ? AND oculto = 0
            ''', (producto_id,))
            
            resultado = cursor.fetchone()
            if resultado:
                stock_actual = float(resultado[0])
                return stock_actual >= cantidad, stock_actual
            return False, 0
        except Exception as e:
            logger.error(f"Error verificando inventario para producto {producto_id}: {e}")
            return False, 0
        finally:
            if 'conn' in locals():
                conn.close()
    
    def crear_venta_whatsapp(self, user_phone: str, items: List[Dict], 
                           direccion: str = None, envio: float = 0) -> Tuple[bool, int, str]:
        """
        Crear una venta a partir de un pedido de WhatsApp
        Integrado con el sistema de ventas existente
        """
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # v13.4: Transacción atómica para toda la venta
            conn.execute("BEGIN")
            
            # Obtener o crear usuario WhatsApp
            usuario_whatsapp_id = self._obtener_o_crear_usuario_whatsapp(user_phone, cursor)
            
            # Obtener o crear cliente asociado
            cliente_id = self._obtener_o_crear_cliente(user_phone, cursor)
            
            # Calcular total
            total = sum(item['subtotal'] for item in items) + envio
            
            # Crear venta en el sistema existente
            fecha_actual = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute('''
                INSERT INTO ventas (fecha, cliente_id, total, forma_pago, usuario)
                VALUES (?, ?, ?, ?, ?)
            ''', (fecha_actual, cliente_id, total, 'EFECTIVO', 'WHATSAPP_BOT'))
            
            venta_id = cursor.lastrowid
            
            # Insertar items y descontar inventario
            for item in items:
                cursor.execute('''
                    INSERT INTO detalles_venta (venta_id, producto_id, cantidad, precio_unitario, total)
                    VALUES (?, ?, ?, ?, ?)
                ''', (venta_id, item['producto_id'], item['cantidad'], item['precio_unitario'], item['subtotal']))
                
                # v13.4: Descontar inventario via app_service si disponible
                try:
                    from core.services.erp_application_service import ERPApplicationService
                    # Crear instancia temporal con la misma conexión
                    _app = ERPApplicationService(db_conn=conn)
                    _app._salida_directa(
                        item['producto_id'], item['cantidad'],
                        'VENTA_WA', f'WA-{venta_id}', 'WHATSAPP_BOT', 1)
                except Exception:
                    # Fallback directo
                    cursor.execute(
                        'UPDATE productos SET existencia = existencia - ? WHERE id = ?',
                        (item['cantidad'], item['producto_id']))
            
            # Registrar movimiento de caja
            cursor.execute('''
                INSERT INTO movimientos_caja (fecha, tipo, monto, descripcion, usuario, venta_id)
                VALUES (?, 'INGRESO', ?, ?, ?, ?)
            ''', (fecha_actual, total, f'Venta WhatsApp #{venta_id}', 'WHATSAPP_BOT', venta_id))
            
            # Actualizar puntos del cliente en sistema existente
            cursor.execute('''
                UPDATE clientes 
                SET puntos = puntos + ?, 
                    compras_acumuladas = compras_acumuladas + ?,
                    ultima_compra = ?
                WHERE id = ?
            ''', (int(total), total, fecha_actual, cliente_id))
            
            # Registrar en historico de puntos
            cursor.execute('''
                INSERT INTO historico_puntos (id_cliente, fecha, tipo, puntos, descripcion, usuario, saldo_actual)
                VALUES (?, ?, 'COMPRA', ?, ?, ?, ?)
            ''', (cliente_id, fecha_actual, int(total), f'Compra WhatsApp #{venta_id}', 'WHATSAPP_BOT', int(total)))
            
            # Crear orden de WhatsApp
            cursor.execute('''
                INSERT INTO whatsapp_orders (user_phone, total, estado, direccion_entrega, costo_envio, venta_id, cliente_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (user_phone, total, 'COMPLETADO', direccion, envio, venta_id, cliente_id))
            
            order_id = cursor.lastrowid
            
            # Insertar items de la orden
            for item in items:
                cursor.execute('''
                    INSERT INTO whatsapp_order_items (order_id, producto_id, producto_nombre, cantidad, precio_unitario, subtotal)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (order_id, item['producto_id'], item['producto_nombre'], item['cantidad'], 
                      item['precio_unitario'], item['subtotal']))
            
            # Acumular puntos en sistema WhatsApp (backup)
            puntos = int(total)
            cursor.execute('''
                INSERT INTO loyalty_points (user_phone, puntos, tipo_movimiento, descripcion, referencia_id)
                VALUES (?, ?, 'ACUMULACION', 'Compra WhatsApp', ?)
            ''', (user_phone, puntos, venta_id))
            
            # Actualizar puntos totales del usuario WhatsApp
            cursor.execute('''
                UPDATE whatsapp_users 
                SET puntos_fidelidad = puntos_fidelidad + ?, updated_at = CURRENT_TIMESTAMP
                WHERE phone_number = ?
            ''', (puntos, user_phone))
            
            conn.commit()
            logger.info(f"Venta WhatsApp creada exitosamente: {venta_id}, Puntos: {puntos}")
            return True, venta_id, "Venta creada exitosamente"
            
        except Exception as e:
            conn.rollback()
            logger.error(f"Error creando venta WhatsApp: {e}")
            return False, 0, f"Error: {str(e)}"
        finally:
            conn.close()
    
    def _obtener_o_crear_usuario_whatsapp(self, phone: str, cursor) -> int:
        """Obtener ID de usuario WhatsApp o crear uno nuevo"""
        cursor.execute('SELECT id FROM whatsapp_users WHERE phone_number = ?', (phone,))
        resultado = cursor.fetchone()
        
        if resultado:
            return resultado[0]
        else:
            cursor.execute('''
                INSERT INTO whatsapp_users (phone_number, nombre, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (phone, f"Cliente WhatsApp {phone}"))
            return cursor.lastrowid
    
    def _obtener_o_crear_cliente(self, phone: str, cursor) -> int:
        """Obtener ID de cliente o crear uno nuevo"""
        nombre_cliente = f"Cliente WhatsApp {phone}"
        
        cursor.execute('SELECT id FROM clientes WHERE telefono = ? OR nombre = ?', (phone, nombre_cliente))
        resultado = cursor.fetchone()
        
        if resultado:
            return resultado[0]
        else:
            cursor.execute('''
                INSERT INTO clientes (nombre, telefono, fecha_creacion)
                VALUES (?, ?, datetime('now'))
            ''', (nombre_cliente, phone))
            return cursor.lastrowid
    
    def obtener_puntos_usuario(self, user_phone: str) -> int:
        """Obtener puntos de fidelidad de un usuario"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Primero intentar obtener de WhatsApp users
            cursor.execute('SELECT puntos_fidelidad FROM whatsapp_users WHERE phone_number = ?', (user_phone,))
            resultado = cursor.fetchone()
            
            if resultado:
                return resultado[0]
            else:
                return 0
        except Exception as e:
            logger.error(f"Error obteniendo puntos: {e}")
            return 0
        finally:
            conn.close()
    
    def obtener_historial_pedidos(self, user_phone: str, limit: int = 10) -> List[Dict]:
        """Obtener historial de pedidos de un usuario"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT wo.id, wo.total, wo.estado, wo.direccion_entrega, wo.created_at
                FROM whatsapp_orders wo
                WHERE wo.user_phone = ?
                ORDER BY wo.created_at DESC
                LIMIT ?
            ''', (user_phone, limit))
            
            pedidos = []
            for row in cursor.fetchall():
                pedidos.append({
                    'id': row[0],
                    'total': float(row[1]),
                    'estado': row[2],
                    'direccion_entrega': row[3],
                    'fecha': row[4]
                })
            return pedidos
        except Exception as e:
            logger.error(f"Error obteniendo historial: {e}")
            return []
        finally:
            conn.close()
    
    def obtener_premios_disponibles(self) -> List[Dict]:
        """Obtener lista de premios disponibles"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, nombre, descripcion, puntos_requeridos, tipo_premio, stock
                FROM rewards 
                WHERE activo = 1 AND (stock IS NULL OR stock > 0)
                ORDER BY puntos_requeridos ASC
            ''')
            
            premios = []
            for row in cursor.fetchall():
                premios.append({
                    'id': row[0],
                    'nombre': row[1],
                    'descripcion': row[2],
                    'puntos_requeridos': row[3],
                    'tipo_premio': row[4],
                    'disponible': row[5] is None or row[5] > 0
                })
            return premios
        except Exception as e:
            logger.error(f"Error obteniendo premios: {e}")
            return []
        finally:
            conn.close()
    def sumar_puntos(self, user_phone: str, puntos: int) -> bool:
        """Sumar puntos a un cliente"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO loyalty_points (user_phone, puntos, tipo_movimiento, descripcion)
                VALUES (?, ?, 'ACUMULACION', ?)
            ''', (user_phone, puntos, f"Bonificación: {puntos} puntos"))
            
            cursor.execute('''
                UPDATE whatsapp_users 
                SET puntos_fidelidad = puntos_fidelidad + ?, updated_at = CURRENT_TIMESTAMP
                WHERE phone_number = ?
            ''', (puntos, user_phone))
            
            conn.commit()
            logger.info(f"✅ Puntos sumados: {puntos} para {user_phone}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error sumando puntos: {e}")
            return False
        finally:
            conn.close()
    
    def canjear_puntos(self, user_phone: str, reward_id: int) -> Tuple[bool, str, Optional[Dict]]:
        """Canjear puntos por un premio"""
        conn = self._get_connection()
        try:
            cursor = conn.cursor()
            
            # Obtener información del premio
            cursor.execute('''
                SELECT id, nombre, puntos_requeridos, tipo_premio, producto_id, porcentaje_descuento, stock
                FROM rewards WHERE id = ? AND activo = 1
            ''', (reward_id,))
            
            premio = cursor.fetchone()
            if not premio:
                return False, "Premio no encontrado", None
            
            premio_id, nombre, puntos_requeridos, tipo_premio, producto_id, porcentaje_descuento, stock = premio
            
            # Verificar stock del premio
            if stock is not None and stock <= 0:
                return False, "Premio agotado", None
            
            # Verificar puntos del usuario
            cursor.execute('SELECT puntos_fidelidad FROM whatsapp_users WHERE phone_number = ?', (user_phone,))
            usuario = cursor.fetchone()
            
            if not usuario or usuario[0] < puntos_requeridos:
                return False, "Puntos insuficientes", None
            
            # Generar código de canje
            codigo_canje = f"CANJE_{user_phone}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Registrar canje
            cursor.execute('''
                INSERT INTO redemptions (user_phone, reward_id, puntos_usados, codigo_canje, fecha_canje)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_phone, reward_id, puntos_requeridos, codigo_canje, date.today()))
            
            # Descontar puntos
            cursor.execute('''
                INSERT INTO loyalty_points (user_phone, puntos, tipo_movimiento, descripcion, referencia_id)
                VALUES (?, ?, 'CANJE', 'Canje: ' || ?, ?)
            ''', (user_phone, -puntos_requeridos, nombre, cursor.lastrowid))
            
            cursor.execute('''
                UPDATE whatsapp_users 
                SET puntos_fidelidad = puntos_fidelidad - ?, updated_at = CURRENT_TIMESTAMP
                WHERE phone_number = ?
            ''', (puntos_requeridos, user_phone))
            
            # Actualizar stock del premio si es aplicable
            if stock is not None:
                cursor.execute('''
                    UPDATE rewards SET stock = stock - 1 WHERE id = ?
                ''', (reward_id,))
            
            conn.commit()
            
            info_premio = {
                'codigo_canje': codigo_canje,
                'nombre': nombre,
                'tipo_premio': tipo_premio,
                'puntos_usados': puntos_requeridos
            }
            
            logger.info(f"✅ Canje exitoso: {user_phone} canjeó {puntos_requeridos} puntos por {nombre}")
            return True, "Canje exitoso", info_premio
            
        except Exception as e:
            conn.rollback()
            logger.error(f"❌ Error en canje: {e}")
            return False, f"Error en canje: {str(e)}", None
        finally:
            conn.close()
 
      