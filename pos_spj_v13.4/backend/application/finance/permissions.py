"""Permisos de Finanzas: vocabulario ``FINANZAS.<accion>`` (prompt maestro §28).

El catálogo global (``permission_catalog``) los toma de aquí; la migración 333
los siembra en ``system_owner`` y ``admin``. Equivalencia con la lista del
prompt (``finance.*`` → ``FINANZAS.*``) en ``finance_refactor_execution_plan.md``
§R2.4. Las acciones de CONTROL (autorizar, ejecutar, contabilizar, revertir,
cerrar, reabrir, castigar, aceptar diferencias, configurar) están separadas de
las de operación para que la segregación de funciones se configure por rol.
"""

from __future__ import annotations


class FinancePermissions:
    VIEW = "FINANZAS.ver"                                   # finance.access
    DASHBOARD_READ = "FINANZAS.tablero.ver"
    EXPORT = "FINANZAS.exportar"                            # finance.statement.export
    # Plan de cuentas
    ACCOUNT_READ = "FINANZAS.cuenta.ver"
    ACCOUNT_MANAGE = "FINANZAS.cuenta.administrar"
    # Asientos
    JOURNAL_READ = "FINANZAS.asiento.ver"
    JOURNAL_CREATE = "FINANZAS.asiento.crear"
    JOURNAL_VALIDATE = "FINANZAS.asiento.validar"
    JOURNAL_POST = "FINANZAS.asiento.contabilizar"
    ENTRY_REVERSE = "FINANZAS.asiento.revertir"
    # Periodos
    PERIOD_READ = "FINANZAS.periodo.ver"
    PERIOD_CLOSE = "FINANZAS.periodo.cerrar"
    PERIOD_REOPEN = "FINANZAS.periodo.reabrir"
    CLOSE_EXCEPTION_AUTHORIZE = "FINANZAS.periodo.autorizar_excepcion"
    ADJUSTMENT_CLOSED_PERIOD = "FINANZAS.ajuste.periodo_cerrado"
    # Cobranza
    RECEIVABLE_READ = "FINANZAS.cxc.ver"
    RECEIVABLE_MANAGE = "FINANZAS.cxc.administrar"
    COLLECTION_REGISTER = "FINANZAS.cobro.registrar"
    COLLECTION_APPLY = "FINANZAS.cobro.aplicar"
    CREDIT_MANAGE = "FINANZAS.credito.administrar"
    WRITE_OFF_AUTHORIZE = "FINANZAS.castigo.autorizar"
    # Cuentas por pagar y pagos (programar → autorizar → ejecutar)
    PAYABLE_READ = "FINANZAS.cxp.ver"
    PAYABLE_MANAGE = "FINANZAS.cxp.administrar"
    PAYABLE_UNBLOCK = "FINANZAS.cxp.desbloquear"
    PAYMENT_SCHEDULE = "FINANZAS.pago.programar"
    PAYMENT_AUTHORIZE = "FINANZAS.pago.autorizar"
    PAYMENT_EXECUTE = "FINANZAS.pago.ejecutar"
    # Tesorería y capital
    TREASURY_READ = "FINANZAS.tesoreria.ver"
    TREASURY_TRANSFER = "FINANZAS.tesoreria.transferir"
    TREASURY_MOVEMENT = "FINANZAS.tesoreria.movimiento"
    TREASURY_MANAGE = "FINANZAS.tesoreria.administrar"
    CAPITAL_REGISTER = "FINANZAS.capital.registrar"
    # Conciliación bancaria
    STATEMENT_IMPORT = "FINANZAS.estado_cuenta.importar"
    RECONCILIATION_OPERATE = "FINANZAS.conciliacion.operar"
    RECONCILIATION_ADJUST = "FINANZAS.conciliacion.ajustar"
    RECONCILIATION_ACCEPT_DIFFERENCE = "FINANZAS.conciliacion.aceptar_diferencia"
    RECONCILIATION_REVERT = "FINANZAS.conciliacion.revertir"
    # Presupuesto y gasto
    BUDGET_READ = "FINANZAS.presupuesto.ver"
    BUDGET_CREATE = "FINANZAS.presupuesto.crear"
    BUDGET_APPROVE = "FINANZAS.presupuesto.aprobar"
    BUDGET_AUTHORIZE_EXCESS = "FINANZAS.presupuesto.autorizar_exceso"
    EXPENSE_REQUEST = "FINANZAS.gasto.solicitar"
    EXPENSE_APPROVE = "FINANZAS.gasto.aprobar"
    EXPENSE_ACCRUE = "FINANZAS.gasto.devengar"
    # Activos
    ASSET_READ = "FINANZAS.activo.ver"
    ASSET_MANAGE = "FINANZAS.activo.administrar"
    ASSET_DEPRECIATE = "FINANZAS.activo.depreciar"
    # Estados, auditoría y configuración
    STATEMENT_READ = "FINANZAS.estados.ver"
    AUDIT_READ = "FINANZAS.auditoria.ver"
    SETTINGS_MANAGE = "FINANZAS.configuracion.administrar"


ALL_FINANCE_PERMISSIONS = frozenset(
    v for k, v in vars(FinancePermissions).items()
    if not k.startswith("_") and isinstance(v, str))

#: Acciones de control: separan a quien opera de quien aprueba o deshace.
FINANCE_CONTROL_PERMISSIONS = frozenset({
    FinancePermissions.JOURNAL_POST,
    FinancePermissions.ENTRY_REVERSE,
    FinancePermissions.PERIOD_CLOSE,
    FinancePermissions.PERIOD_REOPEN,
    FinancePermissions.CLOSE_EXCEPTION_AUTHORIZE,
    FinancePermissions.ADJUSTMENT_CLOSED_PERIOD,
    FinancePermissions.WRITE_OFF_AUTHORIZE,
    FinancePermissions.PAYABLE_UNBLOCK,
    FinancePermissions.PAYMENT_AUTHORIZE,
    FinancePermissions.PAYMENT_EXECUTE,
    FinancePermissions.RECONCILIATION_ADJUST,
    FinancePermissions.RECONCILIATION_ACCEPT_DIFFERENCE,
    FinancePermissions.RECONCILIATION_REVERT,
    FinancePermissions.BUDGET_APPROVE,
    FinancePermissions.BUDGET_AUTHORIZE_EXCESS,
    FinancePermissions.EXPENSE_APPROVE,
    FinancePermissions.SETTINGS_MANAGE,
})
