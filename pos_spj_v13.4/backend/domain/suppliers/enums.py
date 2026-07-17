"""Canonical enums for the suppliers bounded context."""

from __future__ import annotations

from enum import Enum


class SupplierStatus(str, Enum):
    DRAFT = "DRAFT"                      # registro incompleto
    PENDING_APPROVAL = "PENDING_APPROVAL"  # pendiente de autorización
    ACTIVE = "ACTIVE"                    # autorizado
    SUSPENDED = "SUSPENDED"              # pausa temporal
    BLOCKED = "BLOCKED"                  # prohibidas nuevas operaciones
    INACTIVE = "INACTIVE"               # baja operativa (conserva historial)
    REJECTED = "REJECTED"               # solicitud rechazada


class BlockType(str, Enum):
    PURCHASING_BLOCK = "PURCHASING_BLOCK"
    PAYMENT_BLOCK = "PAYMENT_BLOCK"
    RECEIVING_BLOCK = "RECEIVING_BLOCK"
    QUALITY_BLOCK = "QUALITY_BLOCK"
    GENERAL_BLOCK = "GENERAL_BLOCK"


class SupplierClassification(str, Enum):
    """Primary classification (a supplier may hold several)."""

    GOODS = "GOODS"
    SERVICES = "SERVICES"
    LOGISTICS = "LOGISTICS"
    MAINTENANCE = "MAINTENANCE"
    UTILITIES = "UTILITIES"
    PROFESSIONAL_SERVICES = "PROFESSIONAL_SERVICES"
    ASSETS = "ASSETS"
    TECHNOLOGY = "TECHNOLOGY"
    OTHER = "OTHER"


class CommercialCategory(str, Enum):
    """Business categories (a supplier may belong to several)."""

    POULTRY = "POULTRY"
    EGGS = "EGGS"
    GROCERIES = "GROCERIES"
    PACKAGING = "PACKAGING"
    DISPOSABLES = "DISPOSABLES"
    DRIED_CHILES = "DRIED_CHILES"
    CEREALS = "CEREALS"
    BULK_PRODUCTS = "BULK_PRODUCTS"
    CLEANING = "CLEANING"
    TRANSPORT = "TRANSPORT"
    EQUIPMENT = "EQUIPMENT"


class PersonType(str, Enum):
    FISICA = "FISICA"
    MORAL = "MORAL"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RatingGrade(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


class BankAccountStatus(str, Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    BLOCKED = "BLOCKED"


class ContactType(str, Enum):
    SALES = "SALES"
    PURCHASING = "PURCHASING"
    BILLING = "BILLING"
    COLLECTIONS = "COLLECTIONS"
    LOGISTICS = "LOGISTICS"
    QUALITY = "QUALITY"
    MANAGEMENT = "MANAGEMENT"
    EMERGENCY = "EMERGENCY"


class AddressType(str, Enum):
    FISCAL = "FISCAL"
    BILLING = "BILLING"
    SHIPPING = "SHIPPING"
    WAREHOUSE = "WAREHOUSE"
    PICKUP = "PICKUP"
    OFFICE = "OFFICE"
    OTHER = "OTHER"


class DocumentType(str, Enum):
    TAX_STATUS = "TAX_STATUS"                 # constancia fiscal
    COMPLIANCE_OPINION = "COMPLIANCE_OPINION"  # opinión de cumplimiento
    BANK_LETTER = "BANK_LETTER"               # carátula bancaria
    CONTRACT = "CONTRACT"
    ID = "ID"
    ADDRESS_PROOF = "ADDRESS_PROOF"
    SANITARY_CERTIFICATE = "SANITARY_CERTIFICATE"
    PERMIT = "PERMIT"
    INSURANCE = "INSURANCE"
    DATA_SHEET = "DATA_SHEET"
    PRICE_LIST = "PRICE_LIST"
    COMMERCIAL_AGREEMENT = "COMMERCIAL_AGREEMENT"


class DocumentStatus(str, Enum):
    VALID = "VALID"
    EXPIRING = "EXPIRING"
    EXPIRED = "EXPIRED"
    PENDING_REVIEW = "PENDING_REVIEW"
    REJECTED = "REJECTED"


class EvaluationDimension(str, Enum):
    QUALITY = "QUALITY"
    ON_TIME_DELIVERY = "ON_TIME_DELIVERY"
    COMPLETE_QUANTITY = "COMPLETE_QUANTITY"
    PRICE = "PRICE"
    PRICE_VARIATION = "PRICE_VARIATION"
    RESPONSE_TIME = "RESPONSE_TIME"
    DOCUMENTATION = "DOCUMENTATION"
    SERVICE = "SERVICE"
    RETURNS = "RETURNS"
    INCIDENTS = "INCIDENTS"
    SANITARY_COMPLIANCE = "SANITARY_COMPLIANCE"
