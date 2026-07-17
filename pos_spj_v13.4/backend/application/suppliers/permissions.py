"""Granular supplier permission codes (FASE SUP-3 / §28).

Never gate the module with a single general permission — each sensitive action
has its own code (financial data, bank data, verification, audit, export…).
"""

from __future__ import annotations


class SupplierPermissions:
    VIEW = "SUPPLIERS_VIEW"
    CREATE = "SUPPLIERS_CREATE"
    EDIT = "SUPPLIERS_EDIT"
    SUBMIT = "SUPPLIERS_SUBMIT"
    APPROVE = "SUPPLIERS_APPROVE"
    ACTIVATE = "SUPPLIERS_ACTIVATE"
    SUSPEND = "SUPPLIERS_SUSPEND"
    BLOCK = "SUPPLIERS_BLOCK"
    UNBLOCK = "SUPPLIERS_UNBLOCK"
    VIEW_FINANCIAL = "SUPPLIERS_VIEW_FINANCIAL"
    EDIT_TERMS = "SUPPLIERS_EDIT_TERMS"
    VIEW_BANK = "SUPPLIERS_VIEW_BANK"
    EDIT_BANK = "SUPPLIERS_EDIT_BANK"
    VERIFY_BANK = "SUPPLIERS_VERIFY_BANK"
    VIEW_DOCUMENTS = "SUPPLIERS_VIEW_DOCUMENTS"
    UPLOAD_DOCUMENTS = "SUPPLIERS_UPLOAD_DOCUMENTS"
    EVALUATE = "SUPPLIERS_EVALUATE"
    EXPORT = "SUPPLIERS_EXPORT"
    VIEW_AUDIT = "SUPPLIERS_VIEW_AUDIT"


ALL_SUPPLIER_PERMISSIONS = frozenset(
    v for k, v in vars(SupplierPermissions).items()
    if not k.startswith("_") and isinstance(v, str)
)
