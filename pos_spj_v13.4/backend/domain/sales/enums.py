"""Closed Sales/POS domain catalogs (master prompt §10, §16)."""
from enum import Enum


class SaleStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CHECKOUT_PENDING = "CHECKOUT_PENDING"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    RETURNED_PARTIALLY = "RETURNED_PARTIALLY"
    RETURNED_FULLY = "RETURNED_FULLY"
    REVERSED = "REVERSED"


class ProductStockState(str, Enum):
    """§16: the catalog card's stock badge — resolved server-side by
    ProductAvailabilityPolicy/SalesCatalogQueryService, never computed from
    a raw quantity float inside the UI widget."""

    AVAILABLE = "AVAILABLE"
    LOW_STOCK = "LOW_STOCK"
    CRITICAL_STOCK = "CRITICAL_STOCK"
    OUT_OF_STOCK = "OUT_OF_STOCK"
    NOT_SELLABLE = "NOT_SELLABLE"


class PaymentMethod(str, Enum):
    """POS-13/§30-36: the six methods the master prompt names for this phase
    (minus "Mixed", which is not a method of its own — a sale is "mixed"
    when it carries more than one distinct `PaymentMethod` across its
    recorded `SalePayment` lines, exactly how the legacy `forma_pago="Mixto"`
    label is really just shorthand for "more than one line", confirmed by
    reading `SalesService._build_payment_breakdown` before modeling this)."""

    CASH = "CASH"
    CARD = "CARD"
    TRANSFER = "TRANSFER"
    CREDIT = "CREDIT"
    MERCADO_PAGO = "MERCADO_PAGO"


class InvoiceStatus(str, Enum):
    """POS-18/§15: "Fiscal administra CFDI; Clientes administra datos
    maestros; Ventas conserva snapshots históricos." Sales only tracks the
    request/outcome lifecycle of its own invoice requests — it never models
    SAT-specific rejection codes or PAC transport details, those belong to
    a real Fiscal bounded context this repository doesn't have yet
    (confirmed by research: no working PAC integration exists anywhere)."""

    REQUESTED = "REQUESTED"
    ISSUED = "ISSUED"
    ERROR = "ERROR"
    CANCELLED = "CANCELLED"


class ScanContext(str, Enum):
    """POS-12/§17: what a scanned code should be interpreted as. Three real,
    parallel scanner mechanisms exist in `modulos/ventas.py` today
    (`LectorQR`/`LectorQRSerial`, `_ScanContextFilter`, `_scanner_timer`) and
    none of them share a dispatch vocabulary — this is the normalized
    contract `ScanCodeRouter` dispatches on, independent of which of the
    three UI-level mechanisms produced the raw code string."""

    PRODUCT = "PRODUCT"
    CUSTOMER_CARD = "CUSTOMER_CARD"
    AUTO = "AUTO"
