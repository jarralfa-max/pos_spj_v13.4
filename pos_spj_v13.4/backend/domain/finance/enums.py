"""Canonical enumerations for the finance bounded context."""

from __future__ import annotations

from enum import Enum


class AccountType(str, Enum):
    ASSET = "ASSET"
    LIABILITY = "LIABILITY"
    EQUITY = "EQUITY"
    REVENUE = "REVENUE"
    CONTRA_REVENUE = "CONTRA_REVENUE"
    COST_OF_SALES = "COST_OF_SALES"
    EXPENSE = "EXPENSE"
    OTHER_INCOME = "OTHER_INCOME"
    OTHER_EXPENSE = "OTHER_EXPENSE"


class NormalBalance(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


#: Natural balance side for each account type.
NORMAL_BALANCE_BY_TYPE: dict[AccountType, NormalBalance] = {
    AccountType.ASSET: NormalBalance.DEBIT,
    AccountType.LIABILITY: NormalBalance.CREDIT,
    AccountType.EQUITY: NormalBalance.CREDIT,
    AccountType.REVENUE: NormalBalance.CREDIT,
    AccountType.CONTRA_REVENUE: NormalBalance.DEBIT,
    AccountType.COST_OF_SALES: NormalBalance.DEBIT,
    AccountType.EXPENSE: NormalBalance.DEBIT,
    AccountType.OTHER_INCOME: NormalBalance.CREDIT,
    AccountType.OTHER_EXPENSE: NormalBalance.DEBIT,
}


class JournalType(str, Enum):
    SALES = "SALES"
    PURCHASES = "PURCHASES"
    CASH = "CASH"
    BANK = "BANK"
    PAYROLL = "PAYROLL"
    INVENTORY = "INVENTORY"
    LOYALTY = "LOYALTY"
    COMMERCIAL_INSTRUMENTS = "COMMERCIAL_INSTRUMENTS"
    FIXED_ASSETS = "FIXED_ASSETS"
    ADJUSTMENTS = "ADJUSTMENTS"
    GENERAL = "GENERAL"
    OPENING = "OPENING"
    CLOSING = "CLOSING"


class JournalEntryStatus(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    CANCELLED = "CANCELLED"


class FiscalPeriodStatus(str, Enum):
    OPEN = "OPEN"
    SOFT_CLOSED = "SOFT_CLOSED"
    CLOSED = "CLOSED"


class FinancialDocumentType(str, Enum):
    """Documento fuente (§10). El asiento NO sustituye al documento: cada
    documento con impacto económico se relaciona con su asiento, pero son
    responsabilidades distintas."""

    CUSTOMER_INVOICE = "CUSTOMER_INVOICE"
    CUSTOMER_CREDIT_NOTE = "CUSTOMER_CREDIT_NOTE"
    CUSTOMER_ADVANCE = "CUSTOMER_ADVANCE"
    SALES_RETURN = "SALES_RETURN"
    SUPPLIER_INVOICE = "SUPPLIER_INVOICE"
    SUPPLIER_CREDIT_NOTE = "SUPPLIER_CREDIT_NOTE"
    SUPPLIER_ADVANCE = "SUPPLIER_ADVANCE"
    PAYROLL_DOCUMENT = "PAYROLL_DOCUMENT"
    EXPENSE_DOCUMENT = "EXPENSE_DOCUMENT"
    CAPITAL_CONTRIBUTION = "CAPITAL_CONTRIBUTION"
    OWNER_WITHDRAWAL = "OWNER_WITHDRAWAL"
    LOAN = "LOAN"
    LOAN_REPAYMENT = "LOAN_REPAYMENT"
    BANK_CHARGE = "BANK_CHARGE"
    BANK_INTEREST = "BANK_INTEREST"
    BANK_DEPOSIT = "BANK_DEPOSIT"
    BANK_WITHDRAWAL = "BANK_WITHDRAWAL"
    MANUAL_ADJUSTMENT = "MANUAL_ADJUSTMENT"
    ASSET_ACQUISITION = "ASSET_ACQUISITION"
    ASSET_DISPOSAL = "ASSET_DISPOSAL"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"
    WASTE_REPORT = "WASTE_REPORT"
    CASH_SHIFT_CLOSE = "CASH_SHIFT_CLOSE"
    TREASURY_TRANSFER = "TREASURY_TRANSFER"
    LOYALTY_OBLIGATION = "LOYALTY_OBLIGATION"
    LOYALTY_REDEMPTION = "LOYALTY_REDEMPTION"
    COUPON_OBLIGATION = "COUPON_OBLIGATION"
    VOUCHER_OBLIGATION = "VOUCHER_OBLIGATION"
    GIFT_CARD_LIABILITY = "GIFT_CARD_LIABILITY"
    STORED_VALUE_ADJUSTMENT = "STORED_VALUE_ADJUSTMENT"
    PROMOTIONAL_DISCOUNT = "PROMOTIONAL_DISCOUNT"
    COMMERCIAL_INSTRUMENT_EXPIRATION = "COMMERCIAL_INSTRUMENT_EXPIRATION"


class FinancialDocumentStatus(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    PARTIALLY_SETTLED = "PARTIALLY_SETTLED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class ReceivableStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_COLLECTED = "PARTIALLY_COLLECTED"
    COLLECTED = "COLLECTED"
    OVERDUE = "OVERDUE"
    DISPUTED = "DISPUTED"
    CANCELLED = "CANCELLED"
    WRITTEN_OFF = "WRITTEN_OFF"


#: Estados de una CxC que todavía se debe cobrar.
OPEN_RECEIVABLE_STATUSES = frozenset({
    ReceivableStatus.OPEN, ReceivableStatus.PARTIALLY_COLLECTED,
    ReceivableStatus.OVERDUE, ReceivableStatus.DISPUTED,
})


class PayableStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    SCHEDULED = "SCHEDULED"
    AUTHORIZED = "AUTHORIZED"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    DISPUTED = "DISPUTED"
    CANCELLED = "CANCELLED"


#: Estados de una CxP que todavía se debe pagar.
OPEN_PAYABLE_STATUSES = frozenset({
    PayableStatus.OPEN, PayableStatus.PARTIALLY_PAID, PayableStatus.SCHEDULED,
    PayableStatus.AUTHORIZED, PayableStatus.OVERDUE, PayableStatus.DISPUTED,
})


def sql_in(statuses) -> str:
    """Lista SQL literal de estados (constantes del dominio, nunca entrada de usuario)."""
    return "(" + ",".join(f"'{s.value}'" for s in sorted(statuses, key=lambda x: x.value)) + ")"


class PaymentPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SupplierPaymentStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    AUTHORIZED = "AUTHORIZED"
    EXECUTED = "EXECUTED"
    RECONCILED = "RECONCILED"
    CANCELLED = "CANCELLED"


class CollectionStatus(str, Enum):
    """Un cobro registrado se aplica explícitamente a documentos (§11). Lo no
    aplicado es saldo a favor del cliente (anticipo), nunca un cobro perdido."""

    UNAPPLIED = "UNAPPLIED"
    PARTIALLY_APPLIED = "PARTIALLY_APPLIED"
    APPLIED = "APPLIED"
    REVERSED = "REVERSED"


class SupplierAdvanceStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_APPLIED = "PARTIALLY_APPLIED"
    APPLIED = "APPLIED"
    CANCELLED = "CANCELLED"


class PurchaseDebitNature(str, Enum):
    """Naturaleza configurada del débito de una compra (§21): nunca texto libre."""

    INVENTORY = "INVENTORY"
    OPERATING_EXPENSE = "OPERATING_EXPENSE"
    PREPAID_EXPENSE = "PREPAID_EXPENSE"
    FIXED_ASSET = "FIXED_ASSET"
    OTHER_ASSET = "OTHER_ASSET"


class TreasuryAccountType(str, Enum):
    BANK = "BANK"
    CASH_REGISTER = "CASH_REGISTER"
    PETTY_CASH = "PETTY_CASH"
    GENERAL_CASH = "GENERAL_CASH"
    PAYMENT_PROCESSOR = "PAYMENT_PROCESSOR"
    DIGITAL_WALLET = "DIGITAL_WALLET"
    CLEARING_ACCOUNT = "CLEARING_ACCOUNT"


class TreasuryMovementKind(str, Enum):
    """Movimientos de tesorería con documento propio (§13)."""

    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    BANK_CHARGE = "BANK_CHARGE"
    BANK_INTEREST = "BANK_INTEREST"


class ReconciliationStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    REVERTED = "REVERTED"


class StatementLineStatus(str, Enum):
    """Estado de una partida del estado de cuenta (§15)."""

    UNMATCHED = "UNMATCHED"
    SUGGESTED = "SUGGESTED"
    MATCHED = "MATCHED"
    IGNORED = "IGNORED"
    ADJUSTMENT_REQUIRED = "ADJUSTMENT_REQUIRED"


class BudgetStatus(str, Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


#: Presupuestos que controlan el gasto.
CONTROLLING_BUDGET_STATUSES = frozenset({BudgetStatus.APPROVED, BudgetStatus.ACTIVE})


class BudgetControlLevel(str, Enum):
    """Resultado del control presupuestario de una partida (§16)."""

    AVAILABLE = "AVAILABLE"
    WARNING = "WARNING"
    BLOCKING = "BLOCKING"


class ExpenseRequestStatus(str, Enum):
    """Solicitud → aprobación (compromiso) → documento (devengo) → liquidación (pago)."""

    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ACCRUED = "ACCRUED"
    SETTLED = "SETTLED"
    CANCELLED = "CANCELLED"


class FixedAssetStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DISPOSED = "DISPOSED"
    SOLD = "SOLD"
    WRITTEN_OFF = "WRITTEN_OFF"


class DepreciationMethod(str, Enum):
    STRAIGHT_LINE = "STRAIGHT_LINE"


class CapitalMovementKind(str, Enum):
    """Capital, préstamos y CAPEX separados (§17): nada de esto es ingreso."""

    CONTRIBUTION = "CONTRIBUTION"
    WITHDRAWAL = "WITHDRAWAL"
    LOAN_RECEIVED = "LOAN_RECEIVED"
    LOAN_REPAYMENT = "LOAN_REPAYMENT"


class CommercialInstrumentType(str, Enum):
    LOYALTY_POINTS = "LOYALTY_POINTS"
    PROMOTIONAL_COUPON = "PROMOTIONAL_COUPON"
    DISCOUNT_COUPON = "DISCOUNT_COUPON"
    REFUND_VOUCHER = "REFUND_VOUCHER"
    STORE_CREDIT = "STORE_CREDIT"
    GIFT_CARD = "GIFT_CARD"
    PREPAID_VOUCHER = "PREPAID_VOUCHER"
    PROMOTIONAL_BALANCE = "PROMOTIONAL_BALANCE"
    CUSTOMER_WALLET = "CUSTOMER_WALLET"
    THIRD_PARTY_VOUCHER = "THIRD_PARTY_VOUCHER"
    #: Provisión por los premios comprometidos de un sorteo (2026-10-03): el
    #: compromiso nace al activar la campaña y se usa al entregar el premio.
    SWEEPSTAKES_PRIZE = "SWEEPSTAKES_PRIZE"


class CommercialObligationStatus(str, Enum):
    PENDING_RECOGNITION = "PENDING_RECOGNITION"
    OPEN = "OPEN"
    PARTIALLY_REDEEMED = "PARTIALLY_REDEEMED"
    REDEEMED = "REDEEMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"
    REVERSED = "REVERSED"


class RecognitionBasis(str, Enum):
    """How the economic effect of a commercial instrument is recognized."""

    LIABILITY = "LIABILITY"                # real obligation with the customer
    CONTRA_REVENUE = "CONTRA_REVENUE"      # price reduction at redemption
    PROMOTIONAL_EXPENSE = "PROMOTIONAL_EXPENSE"
    THIRD_PARTY_RECEIVABLE = "THIRD_PARTY_RECEIVABLE"  # funded by a supplier/third party
    NO_INITIAL_RECOGNITION = "NO_INITIAL_RECOGNITION"  # recognized only at redemption


class PostingPurpose(str, Enum):
    """Idempotency discriminator: one purpose per economic effect of a source document."""

    SALE_REVENUE = "SALE_REVENUE"
    SALE_COGS = "SALE_COGS"
    SALE_REVERSAL = "SALE_REVERSAL"
    #: Devolución parcial: ingreso/reembolso y su costo (uno por devolución).
    SALE_RETURN = "SALE_RETURN"
    SALE_RETURN_COGS = "SALE_RETURN_COGS"
    PURCHASE_RECEIPT = "PURCHASE_RECEIPT"
    SUPPLIER_INVOICE = "SUPPLIER_INVOICE"
    SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT"
    #: Devolución a proveedor confirmada (auditoría Compras C12).
    SUPPLIER_CREDIT_NOTE = "SUPPLIER_CREDIT_NOTE"
    COLLECTION = "COLLECTION"
    PAYROLL = "PAYROLL"
    #: Préstamo o anticipo de sueldo entregado a un empleado (RR. HH., 2026-10-14).
    EMPLOYEE_LOAN = "EMPLOYEE_LOAN"
    INVENTORY_ADJUSTMENT = "INVENTORY_ADJUSTMENT"
    WASTE = "WASTE"
    PRODUCTION = "PRODUCTION"
    CASH_SHIFT_CLOSE = "CASH_SHIFT_CLOSE"
    CASH_DIFFERENCE = "CASH_DIFFERENCE"
    CASH_DEPOSIT = "CASH_DEPOSIT"
    TREASURY_TRANSFER = "TREASURY_TRANSFER"
    CAPITAL_CONTRIBUTION = "CAPITAL_CONTRIBUTION"
    ASSET_CAPITALIZATION = "ASSET_CAPITALIZATION"
    DEPRECIATION = "DEPRECIATION"
    ASSET_DISPOSAL = "ASSET_DISPOSAL"
    INSTRUMENT_RECOGNITION = "INSTRUMENT_RECOGNITION"
    INSTRUMENT_REDEMPTION = "INSTRUMENT_REDEMPTION"
    INSTRUMENT_EXPIRATION = "INSTRUMENT_EXPIRATION"
    INSTRUMENT_REVERSAL = "INSTRUMENT_REVERSAL"
    PERIOD_CLOSING = "PERIOD_CLOSING"
    OPENING_BALANCE = "OPENING_BALANCE"
    #: Auditoría F11: una CxC/CxP creada desde Finanzas nace con su asiento.
    RECEIVABLE_RECOGNITION = "RECEIVABLE_RECOGNITION"
    PAYABLE_RECOGNITION = "PAYABLE_RECOGNITION"
    REVERSAL = "REVERSAL"
    MANUAL = "MANUAL"
    # ── Ronda 2 FIN-ERP (2026-10-21) ────────────────────────────────────
    CUSTOMER_ADVANCE = "CUSTOMER_ADVANCE"
    CUSTOMER_ADVANCE_APPLICATION = "CUSTOMER_ADVANCE_APPLICATION"
    RECEIVABLE_WRITE_OFF = "RECEIVABLE_WRITE_OFF"
    SUPPLIER_ADVANCE = "SUPPLIER_ADVANCE"
    SUPPLIER_ADVANCE_APPLICATION = "SUPPLIER_ADVANCE_APPLICATION"
    EARLY_PAYMENT_DISCOUNT = "EARLY_PAYMENT_DISCOUNT"
    BANK_DEPOSIT = "BANK_DEPOSIT"
    BANK_WITHDRAWAL = "BANK_WITHDRAWAL"
    BANK_CHARGE = "BANK_CHARGE"
    BANK_INTEREST = "BANK_INTEREST"
    RECONCILIATION_ADJUSTMENT = "RECONCILIATION_ADJUSTMENT"
    LOAN_RECEIVED = "LOAN_RECEIVED"
    LOAN_REPAYMENT = "LOAN_REPAYMENT"
    OWNER_WITHDRAWAL = "OWNER_WITHDRAWAL"
    EXPENSE_ACCRUAL = "EXPENSE_ACCRUAL"
    EXPENSE_SETTLEMENT = "EXPENSE_SETTLEMENT"
    ASSET_SALE = "ASSET_SALE"
    ASSET_WRITE_OFF = "ASSET_WRITE_OFF"
    TRANSFER_SHIPMENT = "TRANSFER_SHIPMENT"
    TRANSFER_RECEIPT = "TRANSFER_RECEIPT"
    TRANSFER_DIFFERENCE = "TRANSFER_DIFFERENCE"


class SettlementType(str, Enum):
    """Means of settlement presented in a sale event payload."""

    CASH = "CASH"
    CARD = "CARD"
    BANK_TRANSFER = "BANK_TRANSFER"
    PAYMENT_PROCESSOR = "PAYMENT_PROCESSOR"
    ON_CREDIT = "ON_CREDIT"
    LOYALTY_POINTS = "LOYALTY_POINTS"
    COUPON = "COUPON"
    VOUCHER = "VOUCHER"
    GIFT_CARD = "GIFT_CARD"
    STORE_CREDIT = "STORE_CREDIT"
    PROMOTIONAL_BALANCE = "PROMOTIONAL_BALANCE"


class LineRole(str, Enum):
    """Papel de una línea. ``ROUNDING`` lleva sólo importe en moneda base: la
    diferencia de redondeo de una conversión va VISIBLE a su cuenta (§24)."""

    NORMAL = "NORMAL"
    ROUNDING = "ROUNDING"


class AuditAction(str, Enum):
    """Acciones auditables de Finanzas (§25)."""

    ACCOUNT_CREATED = "ACCOUNT_CREATED"
    ACCOUNT_UPDATED = "ACCOUNT_UPDATED"
    SETTINGS_UPDATED = "SETTINGS_UPDATED"
    JOURNAL_ENTRY_CREATED = "JOURNAL_ENTRY_CREATED"
    JOURNAL_ENTRY_VALIDATED = "JOURNAL_ENTRY_VALIDATED"
    JOURNAL_ENTRY_POSTED = "JOURNAL_ENTRY_POSTED"
    JOURNAL_ENTRY_CANCELLED = "JOURNAL_ENTRY_CANCELLED"
    JOURNAL_ENTRY_REVERSED = "JOURNAL_ENTRY_REVERSED"
    PERIOD_OPENED = "PERIOD_OPENED"
    PERIOD_CLOSED = "PERIOD_CLOSED"
    PERIOD_REOPENED = "PERIOD_REOPENED"
    RECEIVABLE_CREATED = "RECEIVABLE_CREATED"
    RECEIVABLE_WRITTEN_OFF = "RECEIVABLE_WRITTEN_OFF"
    RECEIVABLE_DISPUTED = "RECEIVABLE_DISPUTED"
    COLLECTION_REGISTERED = "COLLECTION_REGISTERED"
    COLLECTION_APPLIED = "COLLECTION_APPLIED"
    PAYABLE_CREATED = "PAYABLE_CREATED"
    PAYABLE_BLOCKED = "PAYABLE_BLOCKED"
    PAYMENT_SCHEDULED = "PAYMENT_SCHEDULED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_EXECUTED = "PAYMENT_EXECUTED"
    TREASURY_MOVEMENT = "TREASURY_MOVEMENT"
    STATEMENT_IMPORTED = "STATEMENT_IMPORTED"
    RECONCILED = "RECONCILED"
    UNRECONCILED = "UNRECONCILED"
    BUDGET_CHANGED = "BUDGET_CHANGED"
    EXPENSE_DECIDED = "EXPENSE_DECIDED"
    ASSET_CAPITALIZED = "ASSET_CAPITALIZED"
    ASSET_CHANGED = "ASSET_CHANGED"
    DEPRECIATION_RUN = "DEPRECIATION_RUN"
    CAPITAL_MOVEMENT = "CAPITAL_MOVEMENT"
    TAX_CONFIGURED = "TAX_CONFIGURED"
    DATA_EXPORTED = "DATA_EXPORTED"


class TaxKind(str, Enum):
    """Naturaleza fiscal de un código de impuesto (§22)."""

    VAT = "VAT"                              # IVA
    WITHHOLDING_VAT = "WITHHOLDING_VAT"      # retención de IVA
    WITHHOLDING_INCOME = "WITHHOLDING_INCOME"  # retención de ISR
    EXCISE = "EXCISE"                        # IEPS


class TaxDirection(str, Enum):
    SALES = "SALES"          # trasladado
    PURCHASES = "PURCHASES"  # acreditable / retenido


class CashFlowCategory(str, Enum):
    OPERATING = "OPERATING"
    INVESTING = "INVESTING"
    FINANCING = "FINANCING"
    NONE = "NONE"
