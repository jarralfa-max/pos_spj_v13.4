"""Finance bootstrap — siembra la configuración financiera de una base born-clean.

Plan de cuentas jerárquico (§8.1), diarios, periodo vigente, cuentas de
tesorería, perfiles contables, monedas, impuestos configurables, categorías de
activo y configuración inicial. Idempotente: si el catálogo ya existe no toca
nada. No hay "completado tardío" de catálogos anteriores: una base vieja se
regenera (prompt maestro §1).

Account codes are commercial references; identity is always the UUIDv7 id.
Posting profiles are configuration, not code: handlers resolve accounts through
them and never hardcode ids.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.domain.finance.entities.account import Account
from backend.domain.finance.entities.currency import Currency
from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.fixed_asset import FixedAssetCategory
from backend.domain.finance.entities.journal import Journal
from backend.domain.finance.entities.posting_profile import PostingProfile
from backend.domain.finance.entities.tax import TaxCode, TaxPostingProfile, TaxRate
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import (
    AccountType,
    CashFlowCategory,
    CommercialInstrumentType,
    JournalType,
    TaxDirection,
    TaxKind,
    TreasuryAccountType,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

logger = logging.getLogger("spj.finance.bootstrap")

A, L, E = AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY
OP, INV, FIN, NO = (CashFlowCategory.OPERATING, CashFlowCategory.INVESTING,
                    CashFlowCategory.FINANCING, CashFlowCategory.NONE)

#: (code, name, type, cash_flow_category, posting_allowed, parent_code)
CHART: tuple[tuple[str, str, AccountType, CashFlowCategory, bool, str | None], ...] = (
    ("1000", "Activo", A, NO, False, None),
    ("1100", "Activo circulante", A, NO, False, "1000"),
    ("1101", "Caja general", A, OP, True, "1100"),
    ("1102", "Cajas registradoras (POS)", A, OP, True, "1100"),
    ("1103", "Fondo fijo", A, OP, True, "1100"),
    ("1110", "Bancos", A, OP, True, "1100"),
    ("1115", "Procesadores de pago", A, OP, True, "1100"),
    ("1120", "Cuenta puente (partidas por identificar)", A, NO, True, "1100"),
    ("1130", "Clientes (cuentas por cobrar)", A, OP, True, "1100"),
    ("1135", "CxC a terceros financiadores", A, OP, True, "1100"),
    ("1140", "Anticipos a proveedores", A, OP, True, "1100"),
    ("1145", "Préstamos y anticipos a empleados", A, OP, True, "1100"),
    ("1150", "Inventario", A, OP, True, "1100"),
    ("1155", "Producción en proceso", A, OP, True, "1100"),
    ("1160", "Inventario en tránsito", A, OP, True, "1100"),
    ("1170", "IVA acreditable", A, OP, True, "1100"),
    ("1200", "Activo no circulante", A, NO, False, "1000"),
    ("1201", "Activo fijo", A, INV, True, "1200"),
    ("1202", "Depreciación acumulada", A, NO, True, "1200"),
    ("2000", "Pasivo", L, NO, False, None),
    ("2100", "Pasivo circulante", L, NO, False, "2000"),
    ("2101", "Proveedores (cuentas por pagar)", L, OP, True, "2100"),
    ("2110", "IVA trasladado", L, OP, True, "2100"),
    ("2120", "Sueldos por pagar", L, OP, True, "2100"),
    ("2125", "IMSS y cargas sociales por pagar", L, OP, True, "2100"),
    ("2130", "Obligación por puntos de fidelidad", L, NO, True, "2100"),
    ("2131", "Obligación por tarjetas de regalo", L, NO, True, "2100"),
    ("2132", "Obligación por vales pendientes", L, NO, True, "2100"),
    ("2133", "Saldo a favor de clientes (store credit)", L, NO, True, "2100"),
    ("2134", "Saldos promocionales no reembolsables", L, NO, True, "2100"),
    ("2135", "Obligación por monederos de clientes", L, NO, True, "2100"),
    ("2136", "Provisión de premios de sorteos", L, NO, True, "2100"),
    ("2140", "Anticipos de clientes", L, OP, True, "2100"),
    ("2150", "Préstamos por pagar", L, FIN, True, "2100"),
    ("2155", "Retenciones por enterar", L, OP, True, "2100"),
    ("3000", "Capital contable", E, NO, False, None),
    ("3100", "Capital contribuido", E, NO, False, "3000"),
    ("3101", "Capital social", E, FIN, True, "3100"),
    ("3110", "Aportaciones de capital", E, FIN, True, "3100"),
    ("3120", "Retiros de socios", E, FIN, True, "3100"),
    ("3200", "Capital ganado", E, NO, False, "3000"),
    ("3201", "Resultados acumulados", E, NO, True, "3200"),
    ("4000", "Ingresos", AccountType.REVENUE, NO, False, None),
    ("4100", "Ingresos de operación", AccountType.REVENUE, NO, False, "4000"),
    ("4101", "Ingresos por ventas", AccountType.REVENUE, NO, True, "4100"),
    ("4200", "Devoluciones, descuentos y bonificaciones", AccountType.CONTRA_REVENUE, NO,
     False, None),
    ("4201", "Descuentos sobre ventas", AccountType.CONTRA_REVENUE, NO, True, "4200"),
    ("4202", "Contra-ingreso de fidelidad", AccountType.CONTRA_REVENUE, NO, True, "4200"),
    ("4203", "Contra-ingreso por cupones", AccountType.CONTRA_REVENUE, NO, True, "4200"),
    ("4204", "Devoluciones sobre ventas", AccountType.CONTRA_REVENUE, NO, True, "4200"),
    ("5000", "Costos", AccountType.COST_OF_SALES, NO, False, None),
    ("5100", "Costo de ventas", AccountType.COST_OF_SALES, NO, False, "5000"),
    ("5101", "Costo de ventas", AccountType.COST_OF_SALES, NO, True, "5100"),
    ("5110", "Merma", AccountType.COST_OF_SALES, NO, True, "5100"),
    ("5120", "Ajustes de inventario", AccountType.COST_OF_SALES, NO, True, "5100"),
    ("5130", "Diferencias en traspasos entre sucursales", AccountType.COST_OF_SALES, NO,
     True, "5100"),
    ("6000", "Gastos", AccountType.EXPENSE, NO, False, None),
    ("6100", "Gastos de operación", AccountType.EXPENSE, NO, False, "6000"),
    ("6101", "Sueldos y salarios", AccountType.EXPENSE, NO, True, "6100"),
    ("6105", "Cargas sociales (IMSS)", AccountType.EXPENSE, NO, True, "6100"),
    ("6110", "Gasto promocional", AccountType.EXPENSE, NO, True, "6100"),
    ("6111", "Gasto de programa de fidelidad", AccountType.EXPENSE, NO, True, "6100"),
    ("6120", "Depreciación", AccountType.EXPENSE, NO, True, "6100"),
    ("6130", "Gastos operativos", AccountType.EXPENSE, NO, True, "6100"),
    ("6140", "Comisiones bancarias", AccountType.EXPENSE, NO, True, "6100"),
    ("6160", "Cuentas incobrables", AccountType.EXPENSE, NO, True, "6100"),
    ("7000", "Otros ingresos", AccountType.OTHER_INCOME, NO, False, None),
    ("7101", "Otros ingresos operativos", AccountType.OTHER_INCOME, NO, True, "7000"),
    ("7110", "Ingreso por expiración de instrumentos (breakage)", AccountType.OTHER_INCOME,
     NO, True, "7000"),
    ("7120", "Sobrantes de caja", AccountType.OTHER_INCOME, NO, True, "7000"),
    ("7130", "Descuentos por pronto pago obtenidos", AccountType.OTHER_INCOME, NO, True,
     "7000"),
    ("7140", "Utilidad en venta de activos", AccountType.OTHER_INCOME, NO, True, "7000"),
    ("7150", "Intereses ganados", AccountType.OTHER_INCOME, NO, True, "7000"),
    ("7500", "Otros gastos", AccountType.OTHER_EXPENSE, NO, False, None),
    ("7501", "Faltantes de caja", AccountType.OTHER_EXPENSE, NO, True, "7500"),
    ("7510", "Diferencias de redondeo", AccountType.OTHER_EXPENSE, NO, True, "7500"),
    ("7520", "Intereses pagados", AccountType.OTHER_EXPENSE, NO, True, "7500"),
    ("7540", "Pérdida en baja o venta de activos", AccountType.OTHER_EXPENSE, NO, True,
     "7500"),
    ("7590", "Impuestos a la utilidad (ISR)", AccountType.OTHER_EXPENSE, NO, True, "7500"),
)

_RECONCILED = frozenset({"1110", "1115", "1120"})

JOURNALS = (
    (JournalType.SALES, "Ventas", "SAL"),
    (JournalType.PURCHASES, "Compras", "PUR"),
    (JournalType.CASH, "Caja", "CSH"),
    (JournalType.BANK, "Bancos", "BNK"),
    (JournalType.PAYROLL, "Nómina", "PAY"),
    (JournalType.INVENTORY, "Inventario", "INV"),
    (JournalType.LOYALTY, "Fidelidad", "LOY"),
    (JournalType.COMMERCIAL_INSTRUMENTS, "Instrumentos comerciales", "CIN"),
    (JournalType.FIXED_ASSETS, "Activos fijos", "FXA"),
    (JournalType.ADJUSTMENTS, "Ajustes", "ADJ"),
    (JournalType.GENERAL, "General", "GEN"),
    (JournalType.OPENING, "Apertura", "OPN"),
    (JournalType.CLOSING, "Cierre", "CLS"),
)


def finance_catalog_ready(connection) -> bool:
    """¿Ya está sembrada la configuración financiera? (sólo lectura)."""
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='accounts'").fetchone()
    if row is None:
        return False
    return connection.execute(
        "SELECT 1 FROM accounts WHERE code='1101'").fetchone() is not None


def bootstrap_finance(connection, *, today: date | None = None) -> bool:
    """Seed the finance configuration into a clean database (idempotent).

    Devuelve ``True`` si sembró, ``False`` si ya estaba sembrada."""
    today = today or date.today()
    with FinanceUnitOfWork(connection) as uow:
        if uow.accounts.get_by_code("1101") is not None:
            return False
        ids: dict[str, str] = {}
        for code, name, acc_type, cash_flow, posting_allowed, parent in CHART:
            account = Account.create(
                code, name, acc_type, parent_account_id=ids.get(parent) if parent else None,
                posting_allowed=posting_allowed, cash_flow_category=cash_flow,
                reconciliation_required=code in _RECONCILED)
            if parent:
                parent_account = uow.accounts.get(ids[parent])
                parent_account.assert_can_be_parent_of(account)
            uow.accounts.save(account)
            ids[code] = account.id

        for journal_type, name, prefix in JOURNALS:
            uow.journals.save(Journal.create(journal_type, name, prefix))

        if uow.fiscal_periods.find_by_code(today.year, today.month) is None:
            uow.fiscal_periods.save(FiscalPeriod.open_for(today.year, today.month))

        effective = date(today.year, 1, 1)
        _seed_currencies(uow)
        _seed_treasury(uow, ids)
        for profile in posting_profiles(ids, effective):
            uow.posting_profiles.save(profile)
        _seed_taxes(uow, ids, effective)
        _seed_asset_categories(uow, ids)
        uow.settings_store.save(
            uow.settings.with_changes(rounding_account_id=ids["7510"]), updated_by=None)
    logger.info("Finance bootstrap: plan de cuentas, diarios, periodo, tesorería, perfiles,"
                " monedas, impuestos y categorías sembrados.")
    return True


def _seed_currencies(uow: FinanceUnitOfWork) -> None:
    uow.currencies.save(Currency.create("MXN", "Peso mexicano"))
    uow.currencies.save(Currency.create("USD", "Dólar estadounidense"))


def _seed_treasury(uow: FinanceUnitOfWork, ids: dict[str, str]) -> None:
    uow.treasury.save(TreasuryAccount.create(
        "Caja general", TreasuryAccountType.GENERAL_CASH, ids["1101"]))
    uow.treasury.save(TreasuryAccount.create(
        "Banco principal", TreasuryAccountType.BANK, ids["1110"]))
    uow.treasury.save(TreasuryAccount.create(
        "Procesador de tarjetas", TreasuryAccountType.PAYMENT_PROCESSOR, ids["1115"]))


def _seed_taxes(uow: FinanceUnitOfWork, ids: dict[str, str], effective: date) -> None:
    """Códigos de IVA como CONFIGURACIÓN (tasas con vigencia editables). No se
    crea ninguna regla: nada se grava automáticamente hasta que el negocio
    asigne qué código aplica a qué producto o categoría (§22)."""
    for code, name, direction, rate, account in (
            ("IVA16_TRAS", "IVA trasladado 16 %", TaxDirection.SALES, "16", "2110"),
            ("IVA0_TRAS", "IVA trasladado tasa 0 %", TaxDirection.SALES, "0", "2110"),
            ("IVA16_ACRED", "IVA acreditable 16 %", TaxDirection.PURCHASES, "16", "1170"),
            ("IVA0_ACRED", "IVA acreditable tasa 0 %", TaxDirection.PURCHASES, "0", "1170")):
        tax_code = TaxCode.create(code, name, TaxKind.VAT, direction)
        uow.taxes.save_code(tax_code)
        uow.taxes.save_rate(TaxRate.create(tax_code.id, rate, effective))
        uow.taxes.save_posting_profile(TaxPostingProfile.create(tax_code.id, ids[account],
                                                                effective))


def _seed_asset_categories(uow: FinanceUnitOfWork, ids: dict[str, str]) -> None:
    for code, name in (("MOBILIARIO", "Mobiliario y equipo de tienda"),
                       ("REFRIGERACION", "Equipo de refrigeración y proceso"),
                       ("COMPUTO", "Equipo de cómputo y punto de venta"),
                       ("TRANSPORTE", "Equipo de transporte")):
        uow.fixed_assets.save_category(FixedAssetCategory.create(
            code, name, asset_account_id=ids["1201"],
            depreciation_expense_account_id=ids["6120"],
            accumulated_depreciation_account_id=ids["1202"]))


def _profile(key: str, description: str, accounts: dict[str, str], effective: date,
             instrument: CommercialInstrumentType | None = None) -> PostingProfile:
    return PostingProfile.create(key, description, accounts, effective,
                                 instrument_type=instrument)


def posting_profiles(ids: dict[str, str], effective: date) -> list[PostingProfile]:
    """Perfiles contables por omisión (configuración editable, nunca código)."""
    return [
        _profile("SALE", "Ventas (contado/crédito/mixtas)", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "clearing_account_id": ids["1120"],
            "receivable_account_id": ids["1130"],
            "customer_advance_account_id": ids["2140"],
            "write_off_expense_account_id": ids["6160"],
            "revenue_account_id": ids["4101"],
            "discount_account_id": ids["4201"],
            "contra_revenue_account_id": ids["4204"],
            "tax_account_id": ids["2110"],
            "inventory_account_id": ids["1150"],
            "cost_of_sales_account_id": ids["5101"],
            "rounding_account_id": ids["7510"],
        }, effective),
        _profile("PURCHASE", "Compras e inventario", {
            "inventory_account_id": ids["1150"],
            "expense_account_id": ids["6130"],
            "asset_account_id": ids["1201"],
            "payable_account_id": ids["2101"],
            "tax_account_id": ids["1170"],
            "bank_account_id": ids["1110"],
            "cash_account_id": ids["1101"],
            "supplier_advance_account_id": ids["1140"],
            "early_payment_discount_account_id": ids["7130"],
            "retention_account_id": ids["2155"],
        }, effective),
        _profile("PURCHASE_RETURN", "Devoluciones a proveedor (nota de crédito)", {
            "payable_account_id": ids["2101"],
            "inventory_account_id": ids["1150"],
            "supplier_advance_account_id": ids["1140"],
            "tax_account_id": ids["1170"],
        }, effective),
        _profile("PAYROLL", "Nómina", {
            "salary_expense_account_id": ids["6101"],
            "expense_account_id": ids["6105"],
            "salary_payable_account_id": ids["2120"],
            "social_security_payable_account_id": ids["2125"],
            "bank_account_id": ids["1110"],
            # Auditoría RRHH HR-29: la nómina pagada en efectivo sale de caja.
            "cash_account_id": ids["1101"],
            # Abonos a préstamos/anticipos descontados en nómina.
            "employee_receivable_account_id": ids["1145"],
        }, effective),
        _profile("EMPLOYEE_LOAN", "Préstamos y anticipos a empleados (RR. HH.)", {
            "employee_receivable_account_id": ids["1145"],
            "cash_account_id": ids["1101"],
            "bank_account_id": ids["1110"],
        }, effective),
        _profile("INVENTORY", "Ajustes, merma, producción y traspasos", {
            "inventory_account_id": ids["1150"],
            "inventory_adjustment_account_id": ids["5120"],
            "waste_expense_account_id": ids["5110"],
            "production_wip_account_id": ids["1155"],
            "cost_of_sales_account_id": ids["5101"],
            "inventory_in_transit_account_id": ids["1160"],
            "transfer_difference_account_id": ids["5130"],
        }, effective),
        _profile("CASH_SHIFT", "Cortes de caja y diferencias", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "clearing_account_id": ids["1120"],
            "cash_over_account_id": ids["7120"],
            "cash_short_account_id": ids["7501"],
        }, effective),
        _profile("TREASURY", "Tesorería: transferencias, cargos e intereses", {
            "clearing_account_id": ids["1120"],
            "bank_charge_account_id": ids["6140"],
            "bank_interest_account_id": ids["7150"],
            "reconciliation_adjustment_account_id": ids["1120"],
        }, effective),
        _profile("CAPITAL", "Capital, préstamos y retiros", {
            "bank_account_id": ids["1110"],
            "cash_account_id": ids["1101"],
            "capital_account_id": ids["3110"],
            "owner_withdrawal_account_id": ids["3120"],
            "loan_payable_account_id": ids["2150"],
            "loan_interest_account_id": ids["7520"],
        }, effective),
        _profile("FIXED_ASSET", "Activos fijos y depreciación", {
            "asset_account_id": ids["1201"],
            "accumulated_depreciation_account_id": ids["1202"],
            "depreciation_expense_account_id": ids["6120"],
            "bank_account_id": ids["1110"],
            "payable_account_id": ids["2101"],
            "asset_sale_gain_account_id": ids["7140"],
            "asset_sale_loss_account_id": ids["7540"],
        }, effective),
        _profile("INCOME_TAX", "Impuestos a la utilidad (estado de resultados)", {
            "income_tax_expense_account_id": ids["7590"],
        }, effective),
        # Commercial instruments — one profile per instrument nature
        _profile("LOYALTY_POINTS", "Puntos de fidelidad", {
            "contra_revenue_account_id": ids["4202"],
            "expense_account_id": ids["6111"],
            "liability_account_id": ids["2130"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "inventory_account_id": ids["1150"],
            "cost_of_sales_account_id": ids["5101"],
        }, effective, CommercialInstrumentType.LOYALTY_POINTS),
        _profile("GIFT_CARD", "Tarjetas de regalo", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "gift_card_liability_account_id": ids["2131"],
            "liability_account_id": ids["2131"],
            "revenue_account_id": ids["4101"],
            "tax_account_id": ids["2110"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.GIFT_CARD),
        _profile("REFUND_VOUCHER", "Vales por devolución", {
            "contra_revenue_account_id": ids["4204"],
            "liability_account_id": ids["2132"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.REFUND_VOUCHER),
        _profile("PROMOTIONAL_COUPON", "Cupones promocionales", {
            "contra_revenue_account_id": ids["4203"],
            "expense_account_id": ids["6110"],
            "revenue_account_id": ids["4101"],
            "clearing_account_id": ids["1120"],
            "breakage_income_account_id": ids["7110"],
            "liability_account_id": ids["2134"],
            "third_party_receivable_account_id": ids["1135"],
        }, effective, CommercialInstrumentType.PROMOTIONAL_COUPON),
        _profile("STORE_CREDIT", "Saldo a favor del cliente", {
            "contra_revenue_account_id": ids["4204"],
            "liability_account_id": ids["2133"],
            "customer_credit_liability_account_id": ids["2133"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.STORE_CREDIT),
        _profile("PROMOTIONAL_BALANCE", "Saldos promocionales (no efectivo)", {
            "expense_account_id": ids["6110"],
            "promotional_balance_account_id": ids["2134"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
        }, effective, CommercialInstrumentType.PROMOTIONAL_BALANCE),
        _profile("THIRD_PARTY_VOUCHER", "Cupones financiados por terceros", {
            "third_party_receivable_account_id": ids["1135"],
            "liability_account_id": ids["2132"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.THIRD_PARTY_VOUCHER),
        _profile("CUSTOMER_WALLET", "Monederos de clientes", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "liability_account_id": ids["2135"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.CUSTOMER_WALLET),
        # Premios de sorteo: al activar la campaña se provisiona su costo
        # estimado; al entregar el premio la provisión se usa contra el gasto.
        _profile("SWEEPSTAKES_PRIZE", "Premios de sorteos (provisión)", {
            "expense_account_id": ids["6110"],
            "liability_account_id": ids["2136"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
        }, effective, CommercialInstrumentType.SWEEPSTAKES_PRIZE),
        # Vale prepagado vendido en caja: el importe es pasivo (2132), no ingreso.
        _profile("PREPAID_VOUCHER", "Vales prepagados vendidos", {
            "cash_account_id": ids["1102"],
            "liability_account_id": ids["2132"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["7110"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.PREPAID_VOUCHER),
    ]
