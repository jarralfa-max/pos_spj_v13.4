"""Canonical module permission catalog for SPJ POS.

This catalog is the source of truth for module visibility. UI navigation,
Configuración permission matrix and SessionContext checks must all use the same
`MODULO.accion` permission code format.
"""
from __future__ import annotations

CANONICAL_MODULE_PERMISSIONS: dict[str, list[str]] = {
    "DASHBOARD": ["ver"],
    "POS": ["ver", "crear", "cancelar", "descuento"],
    "CAJA": ["ver", "abrir", "cerrar", "retiro", "corte_z"],
    "INVENTARIO": ["ver", "ajustar", "transferir"],
    "TRANSFERENCIAS": ["ver", "crear", "recibir", "cancelar"],
    "PRODUCTOS": ["ver", "crear", "editar", "eliminar"],
    "CLIENTES": ["ver", "crear", "editar", "credito"],
    "MERMA": ["ver", "crear", "autorizar"],
    "DELIVERY": ["ver", "crear", "asignar", "entregar"],
    # Bounded context de Compras (granular; ver backend/application/procurement/permissions.py).
    "COMPRAS": [
        "ver", "ver.sucursal_propia", "ver.sucursales_asignadas", "ver.todas_sucursales",
        "ver.costos", "ver.margenes", "ver.pagos", "ver.credito_proveedor", "ver.auditoria",
        "ver.analitica", "exportar",
        "directa.ver", "directa.crear", "directa.editar", "directa.confirmar",
        "directa.guardar_borrador", "directa.proveedor_ocasional", "directa.crear_producto",
        "directa.sobrescribir_precio", "directa.sobrescribir_costo", "directa.sobre_recibir",
        "directa.cancelar", "directa.reversar", "directa.imprimir",
        "pago.inmediato", "pago.caja_chica", "pago.tesoreria", "pago.transferencia",
        "credito_proveedor.usar", "anticipo.usar", "condiciones.mixtas",
        "limite.sobrescribir", "pago.ver_referencia",
        "solicitud.ver", "solicitud.crear", "solicitud.editar", "solicitud.enviar",
        "solicitud.aprobar", "solicitud.rechazar", "solicitud.cancelar",
        "rfq.crear", "rfq.enviar", "cotizacion.capturar", "cotizacion.editar",
        "cotizacion.comparar", "cotizacion.adjudicar", "cotizacion.sobrescribir_seleccion",
        "orden.ver", "orden.crear", "orden.editar", "orden.enviar_aprobacion",
        "orden.aprobar", "orden.enviar", "orden.confirmar", "orden.versionar",
        "orden.cancelar", "orden.cerrar",
        "recepcion.ver", "recepcion.crear", "recepcion.directa", "recepcion.completar",
        "recepcion.parcial", "recepcion.tolerancia", "recepcion.peso_manual",
        "recepcion.rechazar", "recepcion.reversar", "recepcion.cuarentena",
        "recepcion.devolucion", "calidad.inspeccionar", "calidad.liberar",
        "factura.ver", "factura.capturar", "factura.editar", "factura.conciliar",
        "factura.liberar_diferencia", "factura.bloquear", "factura.cancelar",
    ],
    # Compra en origen / logística de embarques (ver backend/application/logistics/authorization.py).
    "LOGISTICA": [
        "embarque.ver", "embarque.crear", "embarque.despachar", "embarque.forzar",
        "contenedor.gestionar", "contenedor.adjuntar", "contenedor.mover", "contenedor.sellar",
        "contenedor.liberar", "contenedor.escanear", "etiqueta.imprimir",
    ],
    "COTIZACIONES": ["ver", "crear", "aprobar", "convertir"],
    "PRODUCCION": ["ver", "ejecutar"],
    "ETIQUETAS": ["ver", "imprimir"],
    "PLANEACION_COMPRAS": ["ver", "generar"],
    "FINANZAS_UNIFICADAS": ["ver"],
    # Bounded context financiero (nuevo). Los permisos de instrumentos
    # comerciales siguen §24 del contrato: nunca autorizar por nombre de rol.
    "FINANZAS": [
        "ver",
        "asiento.crear",
        "asiento.reversar",
        "periodo.cerrar",
        "periodo.reabrir",
        "cxc.ver",
        "cobro.crear",
        "cxp.ver",
        "pago.programar",
        "pago.autorizar",
        "pago.ejecutar",
        "tesoreria.ver",
        "tesoreria.transferir",
        "conciliacion.ver",
        "conciliacion.ejecutar",
        "presupuesto.ver",
        "presupuesto.aprobar",
        "activo.ver",
        "activo.capitalizar",
        "estados.ver",
        "commercial_obligation.read",
        "commercial_obligation.reconcile",
        "commercial_posting_profile.read",
        "commercial_posting_profile.manage",
        "commercial_adjustment.create",
        "commercial_adjustment.authorize",
    ],
    "ACTIVOS": ["ver", "crear", "mantenimiento"],
    "RRHH": ["ver", "crear", "editar"],
    "GROWTH_ENGINE": ["ver"],
    "TARJETAS_FIDELIDAD": ["ver"],
    "INTELIGENCIA_BI": [
        "ver", "ver_ventas", "ver_inventario", "ver_compras", "ver_caja",
        "ver_clientes", "ver_proveedores", "ver_finanzas", "ver_merma",
        "exportar", "configurar",
    ],
    "WHATSAPP": ["ver"],
    "DISEÑADOR_TICKETS": ["ver"],
    "CONFIG_HARDWARE": ["ver"],
    "CONFIG_MODULOS": ["ver"],
    "CONFIG_SEGURIDAD": ["ver", "editar"],
}


def normalize_permission(code: str) -> str:
    """Normalize permission codes so comparisons are case-insensitive."""
    return str(code or "").strip().upper()


def permission_code(module: str, action: str) -> str:
    """Build a canonical permission code using `MODULE.action` format."""
    return f"{str(module or '').strip().upper()}.{str(action or '').strip().lower()}"


def module_view_permission(module: str) -> str:
    """Return the canonical module visibility permission."""
    return permission_code(module, "ver")
