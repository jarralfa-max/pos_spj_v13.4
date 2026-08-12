"""CreditSaleEligibilityPolicy (§38): "Reglas de venta a crédito: cliente
identificado, no público, perfil autorizado, límite > 0, crédito
disponible, documentos vigentes, no bloqueado, sucursal permitida, permiso
— sin fallback silencioso."

Pure domain logic — no I/O. Two of the nine named checks are deliberately
NOT here: "cliente identificado" (the caller can't call this without
already having resolved a customer_id — there is nothing to check) and
"permiso" (an application-layer ``CustomerAuthorizationPolicy`` concern,
same split as every other rule in this bounded context). The other seven
are evaluated here from caller-supplied facts — this policy never queries
anything itself (no repository access), same "caller loads state, policy
only decides" split as ``CRMStageTransitionPolicy``/
``ServiceLevelPolicyResolver``.

Returns every violation found, never just the first one — "sin fallback
silencioso" means a caller (Ventas/POS) gets the full list to show the
user, not a bare ``False`` they have to guess the reason for.

This bounded context never calls this from POS itself — §38 also says
"Nunca autorizar crédito directo desde POS." Ventas/Finanzas is expected to
call `CheckCreditSaleEligibilityUseCase` (application layer) before
booking a credit sale.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from backend.domain.customer_credit.entities.customer_credit_profile import CustomerCreditProfile
from backend.domain.customer_credit.enums import CreditProfileStatus


@dataclass(frozen=True)
class CreditSaleEligibilityResult:
    eligible: bool
    violations: tuple[str, ...]


class CreditSaleEligibilityPolicy:
    def evaluate(
        self, profile: CustomerCreditProfile | None, *, amount: Decimal,
        is_public_customer: bool, available_credit: Decimal, documents_current: bool,
        branch_allowed: bool,
    ) -> CreditSaleEligibilityResult:
        violations: list[str] = []

        if is_public_customer:
            violations.append("No se puede vender a crédito a público en general")

        if profile is None:
            violations.append("El cliente no tiene un perfil de crédito configurado")
        else:
            if profile.status is not CreditProfileStatus.AUTHORIZED:
                violations.append(
                    f"El perfil de crédito no está autorizado (estado: {profile.status.value})")
            if profile.credit_limit <= 0:
                violations.append("El límite de crédito debe ser mayor a cero")

        if amount <= 0:
            violations.append("El monto debe ser mayor a cero")
        if available_credit < amount:
            violations.append("Crédito disponible insuficiente para el monto solicitado")
        if not documents_current:
            violations.append("Los documentos del cliente no están vigentes")
        if not branch_allowed:
            violations.append("La sucursal no está habilitada para ventas a crédito de este cliente")

        return CreditSaleEligibilityResult(eligible=not violations, violations=tuple(violations))
