
# core/services/asset_service.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AssetService:
    """
    Orquestador de Activos Fijos y Mantenimiento (EAM).
    Conecta los costos de reparación directamente con la Tesorería.
    """
    def __init__(self, db_conn, treasury_service):
        self.db = db_conn
        self.treasury_service = treasury_service

    def registrar_activo(self, nombre: str, categoria: str, numero_serie: str, valor: float, vida_util: int) -> str:
        """Registra un equipo nuevo y le genera su Código Único de Etiqueta."""
        try:
            cursor = self.db.cursor()
            
            # Generamos un código temporal, lo actualizaremos con el ID real
            cursor.execute("""
                INSERT INTO activos (nombre, categoria, numero_serie, valor_adquisicion, vida_util_anios, estado, fecha_adquisicion)
                VALUES (?, ?, ?, ?, ?, 'activo', date('now'))
            """, (nombre, categoria, numero_serie, valor, vida_util))
            
            activo_id = cursor.lastrowid
            
            # Generar Código Corporativo de Etiqueta (Ej. ACT-00015)
            codigo_etiqueta = f"ACT-{str(activo_id).zfill(5)}"
            
            # Si tuviéramos un campo 'codigo' en la tabla activos, lo actualizaríamos aquí.
            # Por ahora, usamos el ID formateado visualmente en la UI, o lo guardamos en notas.
            
            self.db.commit()
            return codigo_etiqueta
            
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Error al registrar el activo: {e}")

    def programar_mantenimiento(self, activo_id: int, tipo: str, descripcion: str, fecha_prog: str):
        """Agenda un mantenimiento preventivo o correctivo."""
        try:
            cursor = self.db.cursor()
            cursor.execute("""
                INSERT INTO mantenimientos (activo_id, tipo, descripcion, fecha_prog, estado)
                VALUES (?, ?, ?, ?, 'pendiente')
            """, (activo_id, tipo, descripcion, fecha_prog))
            self.db.commit()
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"Error agendando mantenimiento: {e}")

    def completar_y_pagar_mantenimiento(self, mantenimiento_id: int, costo: float, tecnico: str, metodo_pago: str, usuario: str, sucursal_id: int):
        """
        Marca el mantenimiento como listo y 🚀 ENVÍA EL GASTO A LA TESORERÍA.
        """
        try:
            import uuid as _u_sp_16f78f
            sp_16f78f = f"sp_{_u_sp_16f78f.uuid4().hex[:6]}"
            self.db.execute(f"SAVEPOINT {sp_16f78f}")
            cursor = self.db.cursor()
            
            # 1. Obtener datos del mantenimiento y del activo para el concepto
            mant = cursor.execute("""
                SELECT m.descripcion, a.nombre as activo_nombre 
                FROM mantenimientos m
                JOIN activos a ON m.activo_id = a.id
                WHERE m.id = ?
            """, (mantenimiento_id,)).fetchone()
            
            # 2. Actualizar el estado a Completado
            cursor.execute("""
                UPDATE mantenimientos 
                SET estado = 'completado', costo = ?, fecha_real = date('now'), realizado_por = ?
                WHERE id = ?
            """, (costo, tecnico, mantenimiento_id))
            
            # 3. 🚀 MAGIA ENTERPRISE: Registrar el Gasto Operativo (OPEX)
            concepto = f"Mantenimiento a {mant['activo_nombre']}: {mant['descripcion']}"
            self.treasury_service.registrar_gasto_opex(
                categoria="Mantenimiento",
                concepto=concepto,
                monto=costo,
                metodo_pago=metodo_pago,
                usuario=usuario,
                sucursal_id=sucursal_id
            )
            
            self.db.execute(f"RELEASE SAVEPOINT {sp_16f78f}")
            logger.info("Mantenimiento #%s completado y pagado.", mantenimiento_id)
        except Exception as e:
            try: self.db.execute(f"ROLLBACK TO SAVEPOINT {sp_16f78f}")
            except Exception: pass
            raise RuntimeError(f"Fallo al procesar el pago del mantenimiento: {e}")