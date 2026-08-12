"""Granular Cash Register permission codes.

Caja uses the same canonical ``MODULO.accion`` vocabulary as Compras,
Inventario and ``core.security.permission_catalog``. These values are stored
directly in ``rol_permisos`` and checked through ``SessionContext.tiene_permiso``;
there is no legacy translation layer.
"""

from __future__ import annotations


class CashPermissions:
    ACCESS = "CAJA.ver"
    VIEW_OWN_BRANCH = "CAJA.ver.sucursal_propia"
    VIEW_ASSIGNED_BRANCHES = "CAJA.ver.sucursales_asignadas"
    VIEW_ALL_BRANCHES = "CAJA.ver.todas_sucursales"
    VIEW_SENSITIVE_AMOUNTS = "CAJA.ver.importes_sensibles"
    AUDIT_VIEW = "CAJA.ver.auditoria"
    EXPORT = "CAJA.exportar"
    REGISTER_VIEW = "CAJA.dispositivo.ver"
    REGISTER_MANAGE = "CAJA.dispositivo.gestionar"
    REGISTER_ACTIVATE = "CAJA.dispositivo.activar"
    REGISTER_BLOCK = "CAJA.dispositivo.bloquear"
    DRAWER_MANAGE = "CAJA.cajon.gestionar"
    TERMINAL_MANAGE = "CAJA.terminal.gestionar"
    SHIFT_VIEW = "CAJA.turno.ver"
    SHIFT_OPEN = "CAJA.turno.abrir"
    SHIFT_SUSPEND = "CAJA.turno.suspender"
    SHIFT_RESUME = "CAJA.turno.reanudar"
    SHIFT_PREPARE_CLOSE = "CAJA.turno.pre_cerrar"
    SHIFT_CLOSE = "CAJA.turno.cerrar"
    SHIFT_FORCE_CLOSE = "CAJA.turno.forzar_cierre"
    MOVEMENT_VIEW = "CAJA.movimiento.ver"
    MOVEMENT_INCOME = "CAJA.movimiento.ingreso"
    MOVEMENT_WITHDRAWAL = "CAJA.movimiento.retiro"
    MOVEMENT_SAFE_DROP = "CAJA.movimiento.safe_drop"
    MOVEMENT_REVERSE = "CAJA.movimiento.reversar"
    MOVEMENT_AUTHORIZE_OVER_LIMIT = "CAJA.movimiento.autorizar_exceso"
    BLIND_COUNT_START = "CAJA.conteo.iniciar"
    BLIND_COUNT_CAPTURE = "CAJA.conteo.capturar"
    BLIND_COUNT_CONFIRM = "CAJA.conteo.confirmar"
    BLIND_COUNT_REVEAL_EXPECTED = "CAJA.conteo.ver_esperado"
    BLIND_COUNT_CANCEL = "CAJA.conteo.cancelar"
    X_CUT_GENERATE = "CAJA.corte_x.generar"
    X_CUT_VIEW = "CAJA.corte_x.ver"
    Z_CUT_GENERATE = "CAJA.corte_z.generar"
    Z_CUT_VIEW = "CAJA.corte_z.ver"
    Z_CUT_REPRINT = "CAJA.corte_z.reimprimir"
    DIFFERENCE_VIEW = "CAJA.diferencia.ver"
    DIFFERENCE_EXPLAIN = "CAJA.diferencia.explicar"
    DIFFERENCE_REVIEW = "CAJA.diferencia.revisar"
    DIFFERENCE_RESOLVE = "CAJA.diferencia.resolver"
    HANDOVER_PREPARE = "CAJA.entrega.preparar"
    HANDOVER_DELIVER = "CAJA.entrega.entregar"
    HANDOVER_RECEIVE = "CAJA.entrega.recibir"
    HANDOVER_DISPUTE = "CAJA.entrega.disputar"
    REFUND_REQUEST = "CAJA.reembolso.solicitar"
    REFUND_AUTHORIZE = "CAJA.reembolso.autorizar"
    DRAWER_OPEN = "CAJA.cajon.abrir"
    DRAWER_OPEN_WITHOUT_SALE = "CAJA.cajon.abrir_sin_venta"
    HARDWARE_DIAGNOSE = "CAJA.hardware.diagnosticar"
    TERMINAL_OPERATE = "CAJA.terminal.operar"
    PRINT = "CAJA.imprimir"
    REPRINT = "CAJA.reimprimir"
    SETTINGS_VIEW = "CAJA.configuracion.ver"
    SETTINGS_MANAGE = "CAJA.configuracion.editar"
    NOTIFICATIONS_MANAGE = "CAJA.notificacion.gestionar"
    SYNC_VIEW = "CAJA.sync.ver"
    SYNC_MANAGE = "CAJA.sync.gestionar"


ALL_CASH_PERMISSIONS = frozenset(
    value for name, value in vars(CashPermissions).items()
    if name.isupper() and isinstance(value, str)
)
