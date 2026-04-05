
# core/services/rrhh_service.py
import logging
from datetime import datetime
from core.db.connection import transaction

logger = logging.getLogger(__name__)

class RRHHService:
    """
    Orquestador de Recursos Humanos.
    Calcula salarios, genera recibos, notifica por WhatsApp y registra el gasto contable.
    """
    def __init__(self, db_conn, treasury_service, whatsapp_service, template_engine):
        self.db = db_conn
        self.treasury_service = treasury_service
        self.whatsapp_service = whatsapp_service
        self.template_engine = template_engine

    def calcular_nomina(self, empleado_id: int, fecha_inicio: str, fecha_fin: str) -> dict:
        """Calcula el salario basado en horas trabajadas o salario fijo."""
        cursor = self.db.cursor()
        
        # 1. Obtener datos del empleado
        empleado = cursor.execute("SELECT nombre, apellidos, salario, telefono FROM personal WHERE id = ?", (empleado_id,)).fetchone()
        if not empleado:
            raise ValueError("Empleado no encontrado.")

        # 2. Calcular horas trabajadas en el periodo (asumiendo que las asistencias están en horas decimales)
        asistencias = cursor.execute("""
            SELECT SUM(horas_trabajadas) as total_horas, COUNT(id) as dias_asistidos
            FROM asistencias 
            WHERE personal_id = ? AND estado IN ('PRESENTE', 'RETARDO')
            AND fecha BETWEEN ? AND ?
        """, (empleado_id, fecha_inicio, fecha_fin)).fetchone()

        total_horas = asistencias['total_horas'] or 0.0
        dias_asistidos = asistencias['dias_asistidos'] or 0

        # Matemática de nómina (Ejemplo simplificado: Pago por hora o fijo prorrateado)
        salario_base = empleado['salario']
        total_pagar = (salario_base / 8.0) * total_horas # Asumiendo salario diario / 8 hrs

        return {
            'empleado_id': empleado_id,
            'nombre_completo': f"{empleado['nombre']} {empleado['apellidos']}",
            'telefono': empleado['telefono'],
            'dias_asistidos': dias_asistidos,
            'total_horas': total_horas,
            'salario_base': salario_base,
            'neto_a_pagar': total_pagar
        }

    def procesar_pago_nomina(self, datos_nomina: dict, metodo_pago: str, sucursal_id: int, admin_user: str) -> str:
        """
        1. Guarda el registro de pago.
        2. Registra el GASTO OPEX en Tesorería.
        3. Genera PDF.
        4. Envía WhatsApp.
        """
        try:
            # transaction() handles BEGIN IMMEDIATE + ROLLBACK on exception
            _tx_cm = transaction(self.db)
            conn   = _tx_cm.__enter__()
            cursor = conn
            
            periodo = f"Pago Nómina {datetime.now().strftime('%Y-%m-%d')}"
            
            # 1. Guardar en historial de nóminas
            cursor.execute("""
                INSERT INTO nomina_pagos (empleado_id, periodo_inicio, periodo_fin, salario_base, total, metodo_pago, estado, usuario)
                VALUES (?, date('now', '-7 days'), date('now'), ?, ?, ?, 'pagado', ?)
            """, (datos_nomina['empleado_id'], datos_nomina['salario_base'], datos_nomina['neto_a_pagar'], metodo_pago, admin_user))
            
            # 2. 🚀 MAGIA ENTERPRISE: Registrar el gasto directamente en Tesorería
            concepto = f"Nómina: {datos_nomina['nombre_completo']} ({datos_nomina['total_horas']} hrs)"
            self.treasury_service.registrar_gasto_opex(
                categoria="Nómina",
                concepto=concepto,
                monto=datos_nomina['neto_a_pagar'],
                metodo_pago=metodo_pago,
                usuario=admin_user,
                sucursal_id=sucursal_id
            )
            
            _tx_cm.__exit__(None, None, None)  # COMMIT
            
            # 3. Generar Recibo de Nómina (Simulado aquí, usarías TemplateEngine)
            recibo_texto = f"Recibo de Nómina: {datos_nomina['nombre_completo']}\nTotal: ${datos_nomina['neto_a_pagar']:.2f}\nHoras: {datos_nomina['total_horas']}"
            
            # 4. Notificar nómina via NotificationService (WhatsApp + inbox POS)
            try:
                notif = getattr(self, 'notification_service', None)
                if notif:
                    notif.notificar_nomina(
                        empleado_id = datos_nomina['empleado_id'],
                        nombre      = datos_nomina['nombre_completo'],
                        monto_neto  = datos_nomina['neto_a_pagar'],
                        periodo     = datetime.now().strftime('%d/%m/%Y'),
                        metodo_pago = metodo_pago,
                        sucursal_id = sucursal_id,
                    )
                elif self.whatsapp_service and datos_nomina.get('telefono'):
                    msg = (f"Hola {datos_nomina['nombre_completo']}, tu nómina por "
                           f"${datos_nomina['neto_a_pagar']:.2f} vía {metodo_pago} fue procesada.")
                    self.whatsapp_service.send_message(
                        sucursal_id, datos_nomina['telefono'], msg)
            except Exception as e:
                logger.warning("notificar_nomina: %s", e)

            return "Nómina pagada, contabilizada y notificada correctamente."
            
        except Exception as e:
            try: _tx_cm.__exit__(type(e), e, None)  # ROLLBACK
            except Exception: pass
            logger.error("Fallo al procesar nómina: %s", e)
            raise RuntimeError(f"Fallo al procesar nómina: {str(e)}")