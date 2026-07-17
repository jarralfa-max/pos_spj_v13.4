"""Domain policies for the suppliers bounded context.

Cross-entity rules that protect the master's invariants: activation workflow,
process blocks, duplicate detection, payment eligibility and separation of
duties. Policies raise ``SupplierDomainError`` subclasses; they never touch I/O.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from backend.domain.suppliers.entities import Supplier, SupplierBankAccount
from backend.domain.suppliers.enums import BankAccountStatus, BlockType, SupplierStatus
from backend.domain.suppliers.exceptions import (
    BankAccountNotVerifiedError,
    RejectedSupplierReactivationError,
    SegregationOfDutiesError,
    SupplierBlockedError,
)


def _normalize_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", text)


class SupplierApprovalPolicy:
    """Separation of duties: the approver cannot be the creator (when enforced)."""

    def __init__(self, *, enforce_segregation: bool = True) -> None:
        self._enforce = enforce_segregation

    def enforce_can_approve(self, supplier: Supplier, approver_user_id: str) -> None:
        if supplier.status is not SupplierStatus.PENDING_APPROVAL:
            from backend.domain.suppliers.exceptions import InvalidSupplierStateError
            raise InvalidSupplierStateError("Solo se aprueba una solicitud pendiente")
        if self._enforce and supplier.created_by_user_id \
                and approver_user_id == supplier.created_by_user_id:
            raise SegregationOfDutiesError(
                "Separación de funciones: quien captura no aprueba el alta")


class SupplierActivationPolicy:
    def enforce_can_activate(self, supplier: Supplier) -> None:
        if supplier.status is SupplierStatus.REJECTED:
            raise RejectedSupplierReactivationError(
                "Un proveedor rechazado requiere un nuevo workflow de alta")


class SupplierBlockPolicy:
    """Maps a block type to the capabilities it disables."""

    _EFFECT = {
        BlockType.PURCHASING_BLOCK: ("purchase",),
        BlockType.PAYMENT_BLOCK: ("pay",),
        BlockType.RECEIVING_BLOCK: ("receive",),
        BlockType.QUALITY_BLOCK: ("receive",),
        BlockType.GENERAL_BLOCK: ("purchase", "receive", "pay"),
    }

    def blocked_capabilities(self, block_type: BlockType) -> tuple[str, ...]:
        return self._EFFECT.get(block_type, ())

    def enforce_can_purchase(self, supplier: Supplier) -> None:
        if not supplier.can_purchase():
            raise SupplierBlockedError(
                "El proveedor no está habilitado para compras (estado o bloqueo)")

    def enforce_can_receive(self, supplier: Supplier) -> None:
        if not supplier.can_receive():
            raise SupplierBlockedError(
                "El proveedor no está habilitado para recepción (estado o bloqueo)")


class SupplierPaymentPolicy:
    def enforce_can_pay(self, supplier: Supplier,
                        bank_account: SupplierBankAccount | None) -> None:
        if not supplier.can_pay():
            raise SupplierBlockedError(
                "El proveedor tiene bloqueo de pagos o estado no pagable")
        if bank_account is None or bank_account.status is not BankAccountStatus.VERIFIED:
            raise BankAccountNotVerifiedError(
                "La cuenta bancaria no está verificada; no se puede pagar")


@dataclass(frozen=True)
class DuplicateMatch:
    supplier_id: str
    reasons: tuple[str, ...]


class SupplierDuplicatePolicy:
    """Detects likely duplicates by RFC / name / phone / email / bank / CLABE.

    Never merges automatically — it only reports candidates for a human decision.
    ``existing`` rows are dicts with keys: id, tax_identifier, legal_name,
    trade_name, phone_e164, email, clabe, account_number.
    """

    def find_matches(self, candidate: dict, existing: list[dict]) -> list[DuplicateMatch]:
        matches: list[DuplicateMatch] = []
        cand_rfc = (candidate.get("tax_identifier") or "").strip().upper()
        cand_name = _normalize_name(candidate.get("legal_name", ""))
        cand_trade = _normalize_name(candidate.get("trade_name", ""))
        cand_phone = re.sub(r"\D", "", candidate.get("phone_e164", "") or "")
        cand_email = (candidate.get("email") or "").strip().lower()
        cand_clabe = re.sub(r"\D", "", candidate.get("clabe", "") or "")
        cand_account = re.sub(r"\D", "", candidate.get("account_number", "") or "")

        for row in existing:
            reasons: list[str] = []
            if cand_rfc and cand_rfc == (row.get("tax_identifier") or "").strip().upper():
                reasons.append("Mismo RFC")
            row_names = {_normalize_name(row.get("legal_name", "")),
                         _normalize_name(row.get("trade_name", ""))}
            if cand_name and cand_name in row_names:
                reasons.append("Misma razón social")
            elif cand_trade and cand_trade in row_names:
                reasons.append("Mismo nombre comercial")
            if cand_phone and cand_phone == re.sub(r"\D", "", row.get("phone_e164", "") or ""):
                reasons.append("Mismo teléfono")
            if cand_email and cand_email == (row.get("email") or "").strip().lower():
                reasons.append("Mismo correo")
            if cand_clabe and cand_clabe == re.sub(r"\D", "", row.get("clabe", "") or ""):
                reasons.append("Misma CLABE")
            elif cand_account and cand_account == re.sub(r"\D", "", row.get("account_number", "") or ""):
                reasons.append("Misma cuenta bancaria")
            if reasons:
                matches.append(DuplicateMatch(row["id"], tuple(reasons)))
        return matches
