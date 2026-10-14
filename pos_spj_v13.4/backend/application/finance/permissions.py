"""Permisos de Finanzas (auditoría d9f2bca F02): vocabulario ``FINANZAS.<accion>``.

Antes la entrada al módulo exigía ``FINANZAS.ver`` y ningún comando exigía nada
más: una sesión de sólo lectura registraba transferencias, y sin sesión se
registraba una aportación. Cada comando que cambia un estado económico exige
ahora su acción. Las acciones de CONTROL (autorizar, ejecutar, revertir, cerrar,
reabrir, aceptar diferencias) están separadas de las de operación para que la
segregación de funciones se configure por rol y no dependa sólo de comparar
identificadores.

La clave ``FINANZAS`` ya existía en el catálogo (la exige el menú). La migración
333 siembra estas acciones sólo en ``system_owner`` y ``admin`` — los únicos
roles que hoy llegan a Finanzas —; abrir el módulo a otros roles es decisión
del negocio y se hace desde la matriz de permisos.
"""

from __future__ import annotations


class FinancePermissions:
    VIEW = "FINANZAS.ver"
    EXPORT = "FINANZAS.exportar"
    # Cobranza
    COLLECTION_REGISTER = "FINANZAS.cobro.registrar"
    RECEIVABLE_CREATE = "FINANZAS.cxc.crear"
    # Pagos a proveedor (programar → autorizar → ejecutar)
    PAYABLE_CREATE = "FINANZAS.cxp.crear"
    PAYMENT_SCHEDULE = "FINANZAS.pago.programar"
    PAYMENT_AUTHORIZE = "FINANZAS.pago.autorizar"
    PAYMENT_EXECUTE = "FINANZAS.pago.ejecutar"
    # Tesorería y capital
    TREASURY_TRANSFER = "FINANZAS.tesoreria.transferir"
    CAPITAL_REGISTER = "FINANZAS.capital.registrar"
    # Conciliación bancaria
    RECONCILIATION_OPERATE = "FINANZAS.conciliacion.operar"
    RECONCILIATION_ACCEPT_DIFFERENCE = "FINANZAS.conciliacion.aceptar_diferencia"
    RECONCILIATION_REVERT = "FINANZAS.conciliacion.revertir"
    # Presupuesto y gasto
    BUDGET_CREATE = "FINANZAS.presupuesto.crear"
    BUDGET_APPROVE = "FINANZAS.presupuesto.aprobar"
    EXPENSE_REQUEST = "FINANZAS.gasto.solicitar"
    EXPENSE_RESOLVE = "FINANZAS.gasto.resolver"
    # Activos
    ASSET_CAPITALIZE = "FINANZAS.activo.capitalizar"
    ASSET_DEPRECIATE = "FINANZAS.activo.depreciar"
    # Asientos y periodos
    ENTRY_REVERSE = "FINANZAS.asiento.revertir"
    PERIOD_CLOSE = "FINANZAS.periodo.cerrar"
    PERIOD_REOPEN = "FINANZAS.periodo.reabrir"
    CLOSE_EXCEPTION_AUTHORIZE = "FINANZAS.periodo.autorizar_excepcion"
    # Configuración contable
    PROFILE_CONFIGURE = "FINANZAS.perfil.configurar"


ALL_FINANCE_PERMISSIONS = frozenset(
    v for k, v in vars(FinancePermissions).items()
    if not k.startswith("_") and isinstance(v, str))

#: Acciones de control: separan a quien opera de quien aprueba o deshace.
FINANCE_CONTROL_PERMISSIONS = frozenset({
    FinancePermissions.PAYMENT_AUTHORIZE,
    FinancePermissions.PAYMENT_EXECUTE,
    FinancePermissions.RECONCILIATION_ACCEPT_DIFFERENCE,
    FinancePermissions.RECONCILIATION_REVERT,
    FinancePermissions.BUDGET_APPROVE,
    FinancePermissions.EXPENSE_RESOLVE,
    FinancePermissions.ENTRY_REVERSE,
    FinancePermissions.PERIOD_CLOSE,
    FinancePermissions.PERIOD_REOPEN,
    FinancePermissions.CLOSE_EXCEPTION_AUTHORIZE,
    FinancePermissions.PROFILE_CONFIGURE,
})
