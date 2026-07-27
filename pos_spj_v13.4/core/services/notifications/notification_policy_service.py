# core/services/notifications/notification_policy_service.py
"""
Decide qué canal de notificación usar para cada tipo de evento.

REGLA:
  El microservicio WhatsApp NO decide a quién notificar.
  El ERP decide mediante esta política.

CANAL WA PARA STAFF — solo si el tipo está en WA_STAFF_ALLOWED.
  - Nómina, vacaciones, descanso → WA al empleado (personal)
  - Alertas críticas / seguridad → WA a responsables configurados
  - Repartidor en ruta → WA al repartidor
  - Forecast / sugerencias → WA a gerentes/compras configurados
  - Clientes → WA siempre

CANAL INBOX ERP — siempre para staff (complementa WA si aplica).
"""
from __future__ import annotations

from typing import FrozenSet

# ── Tipos de notificación que SÍ pueden usar WhatsApp para staff ──────────────
WA_STAFF_ALLOWED: FrozenSet[str] = frozenset({
    # Comunicaciones personales al empleado (RRHH)
    "nomina_pagada",
    "vacaciones_recordatorio",
    "descanso_recordatorio",
    # Alertas críticas de operación a responsables configurados
    "diferencia_caja",          # anomalía financiera → gerente/admin
    "backup_fallido",           # crítico → admin
    "diferencia_recepcion",     # anomalía → admin/inventario (monto alto)
    "alerta_seguridad",         # custom: acceso no autorizado, fraude detectado
    "alerta_operacion_critica", # custom: evento crítico definido por operaciones
    # Logística (repartidor)
    "pedido_asignado_repartidor",
    # Forecast / compras
    "forecast_sugerencia_compra",
})

# ── Tipos de notificación que NO deben llegar por WhatsApp al staff ───────────
# Van SOLO al inbox ERP (notification_inbox).
# Son eventos operativos rutinarios — el staff los ve al iniciar sesión.
WA_STAFF_FORBIDDEN: FrozenSet[str] = frozenset({
    "pedido_nuevo",
    "pedido_whatsapp_nuevo",
    "anticipo_requerido",
    "anticipo_recibido",
    "pedido_cancelado",
    "venta_cancelada",          # cancelación normal — inbox + alerta visual UI
    "pedido_listo",
    "venta_confirmada",
    "cambio_estado_pedido",
    "stock_bajo",
    "corte_z",
    "caducidad_proxima",
})

# Legado: mapeo de constantes de notification_service.py a nombres canónicos
_TIPO_ALIAS: dict[str, str] = {
    "nomina_pagada":             "nomina_pagada",
    "vacaciones_recordatorio":   "vacaciones_recordatorio",
    "descanso_recordatorio":     "descanso_recordatorio",
    "stock_bajo":                "stock_bajo",
    "corte_z":                   "corte_z",
    "venta_cancelada":           "venta_cancelada",
    "diferencia_caja":           "diferencia_caja",
    "diferencia_recepcion":      "diferencia_recepcion",
    "caducidad_proxima":         "caducidad_proxima",
    "backup_fallido":            "backup_fallido",
    "pedido_whatsapp_nuevo":     "pedido_whatsapp_nuevo",
    "pedido_asignado_repartidor": "pedido_asignado_repartidor",
}


class NotificationPolicyService:
    """
    Fuente de verdad sobre qué canal puede recibir cada tipo de notificación.
    Sin dependencias de DB ni estado — consultas puras.
    """

    def is_wa_allowed_for_staff(self, tipo: str) -> bool:
        """
        Retorna True si el tipo de notificación puede enviarse por WhatsApp
        a empleados/staff.

        Clientes: siempre True (no pasar por esta política).
        """
        canonical = _TIPO_ALIAS.get(tipo, tipo)
        if canonical in WA_STAFF_FORBIDDEN:
            return False
        return canonical in WA_STAFF_ALLOWED

    def requires_erp_inbox(self, tipo: str) -> bool:
        """Todo tipo de notificación a staff debe escribirse en el inbox ERP."""
        return True  # siempre

    def channel_summary(self, tipo: str) -> dict:
        """Debug / auditoría: canales asignados para un tipo."""
        wa = self.is_wa_allowed_for_staff(tipo)
        return {
            "tipo":       tipo,
            "erp_inbox":  True,
            "whatsapp":   wa,
            "reason":     (
                "allowed" if wa
                else ("forbidden" if tipo in WA_STAFF_FORBIDDEN else "not_in_allowlist")
            ),
        }
