"""Ports: narrow read contracts Procurement depends on from other bounded
contexts (Products, Logistics, Suppliers, Finance, Inventory). A use case or
presenter type-hints against these Protocols, never against the concrete
service in the other context; the concrete adapter is wired at the
composition root (``enterprise_routes.py`` / ``direct_purchase_routes.py``).

Structural typing (``Protocol``): an existing service satisfies a port simply
by having the right method signature — no inheritance required. That is why
``WarehouseDirectoryQueryService`` (owned by Logistics) already satisfies
``BranchWarehouseContextPort`` unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class ProcurementProductOption:
    product_id: str
    code: str
    name: str
    purchase_unit: str | None
    purchasable: bool
    #: Informativo: Compras busca en el catálogo GLOBAL; esto sólo dice si el
    #: producto está habilitado en la sucursal consultada (None = no se sabe).
    enabled_in_branch: bool | None = None


@dataclass(frozen=True)
class PurchaseUnitOption:
    """``1 code = factor_to_base`` unidades base del producto."""

    code: str
    name: str
    factor_to_base: Decimal
    dimension: str = ""
    is_base: bool = False
    #: §27 (de Productos): ¿se puede recibir en fracción?
    fractional_receipt: bool = True


@dataclass(frozen=True)
class PurchaseProductProfile:
    """Lo que Compras necesita de Productos para capturar una línea: unidad base
    (la de inventario), unidades de compra con su conversión y base de precio.
    Compras sólo LEE esto; nunca inventa ni deja editar unidades o factores."""

    product_id: str
    code: str
    name: str
    base_unit: str
    base_unit_name: str
    base_unit_dimension: str
    units: tuple[PurchaseUnitOption, ...]
    purchasable: bool = True
    catch_weight: bool = False
    price_basis: str | None = None
    lot_controlled: bool = False
    expiration_controlled: bool = False
    temperature_tracked: bool = False
    serial_tracked: bool = False

    def unit(self, code: str | None) -> PurchaseUnitOption | None:
        wanted = (code or self.base_unit or "").strip().upper()
        for option in self.units:
            if option.code.upper() == wanted:
                return option
        return None


class ProcurementProductCatalogPort(Protocol):
    """Read-only access to the canonical product catalog (§11), scoped to
    products Compras may buy. Never reads the legacy ``productos`` table —
    see ``SearchPurchasableProductsQueryService``."""

    def search(self, query: str, *, branch_id: str | None = None,
               limit: int = 20) -> list[ProcurementProductOption]:
        ...

    def resolve(self, product_id: str) -> ProcurementProductOption | None:
        ...

    def purchase_profile(self, product_id: str) -> PurchaseProductProfile | None:
        ...


class BranchWarehouseContextPort(Protocol):
    """Read-only lookup of the warehouses a branch may receive purchases
    into. Owned by Logistics (``WarehouseDirectoryQueryService``); Procurement
    only ever reads through this port, never the ``warehouses`` table itself."""

    def active_for_branch(self, branch_id: str) -> list[tuple[str, str]]:
        ...


@dataclass(frozen=True)
class SupplierProcurementProfile:
    supplier_id: str
    legal_name: str
    trade_name: str | None
    status: str
    purchasing_enabled: bool
    financially_blocked: bool
    risk_level: str | None
    rating_grade: str | None
    active_blocks: tuple[str, ...]


class SupplierProcurementProfilePort(Protocol):
    """Read-only commercial/eligibility profile of a supplier, owned by
    Suppliers. Satisfied by an adapter composing
    ``SupplierDetailQueryService.get_header()`` +
    ``SupplierDirectoryQueryService.get_eligibility()`` — Procurement never
    reads ``supplier_master``/``proveedores`` directly."""

    def profile(self, supplier_id: str) -> SupplierProcurementProfile | None:
        ...


@dataclass(frozen=True)
class SupplierFinancialStanding:
    supplier_id: str
    balance: str
    overdue: str
    open_documents: int


class ProcurementFinancePort(Protocol):
    """Read-only financial standing of a supplier (payable balance/overdue),
    owned by Finance. Satisfied structurally by
    ``SupplierFinancialSummaryQueryService`` — Procurement never reads the
    ``payables`` table directly."""

    def financial_standing(self, supplier_id: str) -> SupplierFinancialStanding:
        ...


@dataclass(frozen=True)
class InventoryReceiptStatus:
    goods_receipt_id: str
    status: str | None
    occurred_at: str | None


class InventoryReceiptStatusPort(Protocol):
    """Read-only posting status of a goods receipt into inventory, owned by
    Inventory. Satisfied structurally by ``ReceiptQueryService`` — Procurement
    never reads ``inventory_ledger`` directly."""

    def status_for_receipt(self, goods_receipt_id: str) -> InventoryReceiptStatus | None:
        ...


class PaymentSourceBookingPort(Protocol):
    """¿Se puede CONTABILIZAR un pago de contado desde esta fuente?

    Owned by Finance. Compras sólo pregunta: devuelve `None` si el pago tiene
    cuenta de tesorería y perfil contable donde asentarse, o el motivo si no.
    Existe porque confirmar una compra de contado cuyo pago no se puede asentar
    sacaba dinero sin asiento contable (CLAUDE.md §11).
    """

    def booking_problem(self, payment_source: str, branch_id: str | None) -> str | None:
        ...


class SupplierPaymentTermsPort(Protocol):
    """Días de crédito pactados con el proveedor. Owned by Suppliers.

    Para el vencimiento de la cuenta por pagar: fecha de factura + estos días.
    `0` si el proveedor es de contado o no tiene condiciones capturadas.
    """

    def credit_days(self, supplier_id: str) -> int:
        ...
