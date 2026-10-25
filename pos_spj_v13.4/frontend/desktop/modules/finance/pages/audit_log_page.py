"""Bitácora de auditoría financiera (§25): quién, qué, cuándo, antes y después
de cada operación financiera. Sólo lectura."""

from __future__ import annotations

from frontend.desktop.components.tables import ColumnSpec
from frontend.desktop.modules.finance.pages._page_base import FinancePage

_ENTITIES = [("journal_entry", "Asientos"), ("fiscal_period", "Periodos"),
             ("close_exception", "Diferencias de cierre"), ("account", "Cuentas"),
             ("receivable", "CxC"), ("collection", "Cobros"), ("payable", "CxP"),
             ("supplier_payment", "Pagos"), ("supplier_advance", "Anticipos"),
             ("treasury_account", "Cuentas de tesorería"),
             ("treasury_transfer", "Transferencias"), ("treasury_movement", "Movimientos"),
             ("capital_transaction", "Capital"), ("bank_statement", "Estados de cuenta"),
             ("bank_statement_line", "Partidas de estado"),
             ("reconciliation", "Conciliaciones"), ("budget", "Presupuestos"),
             ("expense_request", "Gastos"), ("expense_approval_rule", "Reglas de gasto"),
             ("fixed_asset", "Activos"), ("depreciation_run", "Depreciación"),
             ("finance_settings", "Parámetros"), ("posting_profile", "Perfiles contables"),
             ("tax_code", "Impuestos"), ("exchange_rate", "Tipos de cambio"),
             ("export", "Exportaciones")]


class AuditLogPage(FinancePage):
    title = "Auditoría financiera"
    subtitle = "Bitácora inmutable de operaciones financieras"
    searchable = True
    paginated = True
    status_filter = _ENTITIES
    columns = [
        ColumnSpec("Fecha", "date"),
        ColumnSpec("Acción", "status"),
        ColumnSpec("Entidad", "status"),
        ColumnSpec("Registro", "date"),
        ColumnSpec("Usuario", "date"),
        ColumnSpec("Motivo"),
        ColumnSpec("Cambios"),
    ]

    def _load(self) -> None:
        model = self._presenter.audit_log(entity_type=self._status_id(),
                                          search=self._search.query(),
                                          limit=self.page_size, offset=self.offset)
        self.set_table(model)
        # La bitácora no tiene total del servidor: «Siguiente» se habilita
        # mientras la página venga llena.
        self._total = self.offset + len(model.rows) + (1 if len(model.rows) ==
                                                        self.page_size else 0)
