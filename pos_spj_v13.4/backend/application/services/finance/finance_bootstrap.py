"""Finance bootstrap — seeds the chart of accounts, journals, current fiscal
period and default posting profiles into a born-clean database. Idempotent.

Account codes are commercial references; identity is always the UUIDv7 id.
Posting profiles are configuration, not code: handlers resolve accounts through
them and never hardcode ids.
"""

from __future__ import annotations

import logging
from datetime import date

from backend.domain.finance.entities.account import Account
from backend.domain.finance.entities.fiscal_period import FiscalPeriod
from backend.domain.finance.entities.journal import Journal
from backend.domain.finance.entities.posting_profile import PostingProfile
from backend.domain.finance.entities.treasury_account import TreasuryAccount
from backend.domain.finance.enums import (
    AccountType,
    CashFlowCategory,
    CommercialInstrumentType,
    JournalType,
    TreasuryAccountType,
)
from backend.infrastructure.db.repositories.finance.unit_of_work import FinanceUnitOfWork

logger = logging.getLogger("spj.finance.bootstrap")

#: (code, name, type, cash_flow_category, posting_allowed)
_CHART = (
    # Assets
    ("1101", "Caja general", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1102", "Cajas registradoras (POS)", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1103", "Fondo fijo", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1110", "Bancos", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1115", "Procesadores de pago", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1120", "Cuenta puente (clearing)", AccountType.ASSET, CashFlowCategory.NONE, True),
    ("1130", "Clientes (cuentas por cobrar)", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1135", "CxC a terceros financiadores", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1140", "Anticipos a proveedores", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1150", "Inventario", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1155", "Producción en proceso", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1160", "Inventario en tránsito", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1170", "IVA acreditable", AccountType.ASSET, CashFlowCategory.OPERATING, True),
    ("1201", "Activo fijo", AccountType.ASSET, CashFlowCategory.INVESTING, True),
    ("1202", "Depreciación acumulada", AccountType.ASSET, CashFlowCategory.NONE, True),
    # Liabilities
    ("2101", "Proveedores (cuentas por pagar)", AccountType.LIABILITY, CashFlowCategory.OPERATING, True),
    ("2110", "IVA trasladado", AccountType.LIABILITY, CashFlowCategory.OPERATING, True),
    ("2120", "Sueldos por pagar", AccountType.LIABILITY, CashFlowCategory.OPERATING, True),
    ("2125", "IMSS y cargas sociales por pagar", AccountType.LIABILITY, CashFlowCategory.OPERATING, True),
    ("2130", "Obligación por puntos de fidelidad", AccountType.LIABILITY, CashFlowCategory.NONE, True),
    ("2131", "Obligación por tarjetas de regalo", AccountType.LIABILITY, CashFlowCategory.NONE, True),
    ("2132", "Obligación por vales pendientes", AccountType.LIABILITY, CashFlowCategory.NONE, True),
    ("2133", "Saldo a favor de clientes (store credit)", AccountType.LIABILITY, CashFlowCategory.NONE, True),
    ("2134", "Saldos promocionales no reembolsables", AccountType.LIABILITY, CashFlowCategory.NONE, True),
    ("2135", "Obligación por monederos de clientes", AccountType.LIABILITY, CashFlowCategory.NONE, True),
    ("2140", "Anticipos de clientes", AccountType.LIABILITY, CashFlowCategory.OPERATING, True),
    ("2150", "Préstamos por pagar", AccountType.LIABILITY, CashFlowCategory.FINANCING, True),
    # Equity
    ("3101", "Capital social", AccountType.EQUITY, CashFlowCategory.FINANCING, True),
    ("3110", "Aportaciones de capital", AccountType.EQUITY, CashFlowCategory.FINANCING, True),
    ("3201", "Resultados acumulados", AccountType.EQUITY, CashFlowCategory.NONE, True),
    # Revenue
    ("4101", "Ingresos por ventas", AccountType.REVENUE, CashFlowCategory.NONE, True),
    ("4110", "Otros ingresos operativos", AccountType.OTHER_INCOME, CashFlowCategory.NONE, True),
    ("4120", "Ingreso por expiración de instrumentos (breakage)", AccountType.OTHER_INCOME, CashFlowCategory.NONE, True),
    ("4130", "Sobrantes de caja", AccountType.OTHER_INCOME, CashFlowCategory.NONE, True),
    # Contra revenue
    ("4201", "Descuentos sobre ventas", AccountType.CONTRA_REVENUE, CashFlowCategory.NONE, True),
    ("4202", "Contra-ingreso de fidelidad", AccountType.CONTRA_REVENUE, CashFlowCategory.NONE, True),
    ("4203", "Contra-ingreso por cupones", AccountType.CONTRA_REVENUE, CashFlowCategory.NONE, True),
    ("4204", "Devoluciones sobre ventas", AccountType.CONTRA_REVENUE, CashFlowCategory.NONE, True),
    # Cost of sales
    ("5101", "Costo de ventas", AccountType.COST_OF_SALES, CashFlowCategory.NONE, True),
    ("5110", "Merma", AccountType.COST_OF_SALES, CashFlowCategory.NONE, True),
    ("5120", "Ajustes de inventario", AccountType.COST_OF_SALES, CashFlowCategory.NONE, True),
    # Expenses
    ("6101", "Sueldos y salarios", AccountType.EXPENSE, CashFlowCategory.NONE, True),
    ("6105", "Cargas sociales (IMSS)", AccountType.EXPENSE, CashFlowCategory.NONE, True),
    ("6110", "Gasto promocional", AccountType.EXPENSE, CashFlowCategory.NONE, True),
    ("6111", "Gasto de programa de fidelidad", AccountType.EXPENSE, CashFlowCategory.NONE, True),
    ("6120", "Depreciación", AccountType.EXPENSE, CashFlowCategory.NONE, True),
    ("6130", "Gastos operativos", AccountType.EXPENSE, CashFlowCategory.NONE, True),
    ("6140", "Faltantes de caja", AccountType.OTHER_EXPENSE, CashFlowCategory.NONE, True),
    ("6150", "Redondeos", AccountType.OTHER_EXPENSE, CashFlowCategory.NONE, True),
)

_JOURNALS = (
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


def bootstrap_finance(connection, *, today: date | None = None) -> None:
    """Seed the finance configuration into a clean database (idempotent)."""
    today = today or date.today()
    with FinanceUnitOfWork(connection) as uow:
        if uow.accounts.get_by_code("1101") is not None:
            logger.info("Finance bootstrap: chart already seeded; skipping")
            return
        code_to_id: dict[str, str] = {}
        for code, name, acc_type, cash_flow, posting_allowed in _CHART:
            account = Account.create(
                code, name, acc_type,
                posting_allowed=posting_allowed,
                cash_flow_category=cash_flow,
                reconciliation_required=code in ("1110", "1115", "1120"),
            )
            uow.accounts.save(account)
            code_to_id[code] = account.id

        for journal_type, name, prefix in _JOURNALS:
            uow.journals.save(Journal.create(journal_type, name, prefix))

        if uow.fiscal_periods.find_by_code(today.year, today.month) is None:
            uow.fiscal_periods.save(FiscalPeriod.open_for(today.year, today.month))

        _seed_treasury(uow, code_to_id)
        _seed_posting_profiles(uow, code_to_id, today)
    logger.info("Finance bootstrap: chart, journals, period, treasury and profiles seeded.")


def _seed_treasury(uow: FinanceUnitOfWork, ids: dict[str, str]) -> None:
    uow.treasury.save(TreasuryAccount.create(
        "Caja general", TreasuryAccountType.GENERAL_CASH, ids["1101"]))
    uow.treasury.save(TreasuryAccount.create(
        "Banco principal", TreasuryAccountType.BANK, ids["1110"]))
    uow.treasury.save(TreasuryAccount.create(
        "Procesador de tarjetas", TreasuryAccountType.PAYMENT_PROCESSOR, ids["1115"]))


def _profile(key: str, description: str, accounts: dict[str, str], effective: date,
             instrument: CommercialInstrumentType | None = None) -> PostingProfile:
    return PostingProfile.create(key, description, accounts, effective,
                                 instrument_type=instrument)


def _seed_posting_profiles(uow: FinanceUnitOfWork, ids: dict[str, str], today: date) -> None:
    effective = date(today.year, 1, 1)
    profiles = [
        _profile("SALE", "Ventas (contado/crédito/mixtas)", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "clearing_account_id": ids["1120"],
            "receivable_account_id": ids["1130"],
            "revenue_account_id": ids["4101"],
            "discount_account_id": ids["4201"],
            "contra_revenue_account_id": ids["4204"],
            "tax_account_id": ids["2110"],
            "inventory_account_id": ids["1150"],
            "cost_of_sales_account_id": ids["5101"],
            "rounding_account_id": ids["6150"],
        }, effective),
        _profile("PURCHASE", "Compras e inventario", {
            "inventory_account_id": ids["1150"],
            "payable_account_id": ids["2101"],
            "tax_account_id": ids["1170"],
            "bank_account_id": ids["1110"],
            "cash_account_id": ids["1101"],
        }, effective),
        _profile("PAYROLL", "Nómina", {
            "salary_expense_account_id": ids["6101"],
            "expense_account_id": ids["6105"],
            "salary_payable_account_id": ids["2120"],
            "social_security_payable_account_id": ids["2125"],
            "bank_account_id": ids["1110"],
        }, effective),
        _profile("INVENTORY", "Ajustes, merma y producción", {
            "inventory_account_id": ids["1150"],
            "inventory_adjustment_account_id": ids["5120"],
            "waste_expense_account_id": ids["5110"],
            "production_wip_account_id": ids["1155"],
            "cost_of_sales_account_id": ids["5101"],
        }, effective),
        _profile("CASH_SHIFT", "Cortes de caja y diferencias", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "clearing_account_id": ids["1120"],
            "cash_over_short_account_id": ids["6140"],
            "breakage_income_account_id": ids["4130"],
        }, effective),
        _profile("TREASURY", "Transferencias de tesorería", {
            "clearing_account_id": ids["1120"],
        }, effective),
        _profile("CAPITAL", "Aportaciones de capital", {
            "bank_account_id": ids["1110"],
            "cash_account_id": ids["1101"],
            "capital_account_id": ids["3110"],
        }, effective),
        _profile("FIXED_ASSET", "Activos fijos y depreciación", {
            "asset_account_id": ids["1201"],
            "accumulated_depreciation_account_id": ids["1202"],
            "depreciation_expense_account_id": ids["6120"],
            "bank_account_id": ids["1110"],
            "payable_account_id": ids["2101"],
        }, effective),
        # Commercial instruments — one profile per instrument nature
        _profile("LOYALTY_POINTS", "Puntos de fidelidad", {
            "contra_revenue_account_id": ids["4202"],
            "expense_account_id": ids["6111"],
            "liability_account_id": ids["2130"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["4120"],
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
            "breakage_income_account_id": ids["4120"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.GIFT_CARD),
        _profile("REFUND_VOUCHER", "Vales por devolución", {
            "contra_revenue_account_id": ids["4204"],
            "liability_account_id": ids["2132"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["4120"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.REFUND_VOUCHER),
        _profile("PROMOTIONAL_COUPON", "Cupones promocionales", {
            "contra_revenue_account_id": ids["4203"],
            "expense_account_id": ids["6110"],
            "revenue_account_id": ids["4101"],
            "clearing_account_id": ids["1120"],
            "breakage_income_account_id": ids["4120"],
            "liability_account_id": ids["2134"],
            "third_party_receivable_account_id": ids["1135"],
        }, effective, CommercialInstrumentType.PROMOTIONAL_COUPON),
        _profile("STORE_CREDIT", "Saldo a favor del cliente", {
            "contra_revenue_account_id": ids["4204"],
            "liability_account_id": ids["2133"],
            "customer_credit_liability_account_id": ids["2133"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["4120"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.STORE_CREDIT),
        _profile("PROMOTIONAL_BALANCE", "Saldos promocionales (no efectivo)", {
            "expense_account_id": ids["6110"],
            "promotional_balance_account_id": ids["2134"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["4120"],
            "clearing_account_id": ids["1120"],
        }, effective, CommercialInstrumentType.PROMOTIONAL_BALANCE),
        _profile("THIRD_PARTY_VOUCHER", "Cupones financiados por terceros", {
            "third_party_receivable_account_id": ids["1135"],
            "liability_account_id": ids["2132"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["4120"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.THIRD_PARTY_VOUCHER),
        _profile("CUSTOMER_WALLET", "Monederos de clientes", {
            "cash_account_id": ids["1102"],
            "bank_account_id": ids["1110"],
            "liability_account_id": ids["2135"],
            "revenue_account_id": ids["4101"],
            "breakage_income_account_id": ids["4120"],
            "clearing_account_id": ids["1120"],
            "expense_account_id": ids["6110"],
        }, effective, CommercialInstrumentType.CUSTOMER_WALLET),
    ]
    for profile in profiles:
        uow.posting_profiles.save(profile)
