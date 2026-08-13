"""CustomerDataQualityService — evaluates §46's rule list against a
customer record.

Deliberately scoped to the subset of §46's rules that only need
``customers``' own data (name, phone, email, RFC, address) — reusing the
existing PhoneNumber/EmailAddress value objects for validity (their
``__post_init__`` already raises on malformed input, no need to
reimplement the same regex here) plus a lightweight RFC shape check (no
dedicated value object exists for it in this codebase yet; a full
checksum-validating RFC type would be over-engineering for what is meant
to be a soft quality *heuristic*, not a hard validation gate).

Five §46 rules are intentionally NOT evaluated here: "consentimiento
faltante" (customer_privacy), "crédito inconsistente" (customer_credit),
"lead sin seguimiento"/"oportunidad sin próxima actividad" (crm), "caso
sin propietario" (customer_service) — each needs another bounded
context's data, and this package doesn't reach into those tables (same
boundary CRM-8's CxC query and this same phase's merge use case hold).
CRM-12 (Customer 360) is the natural place to aggregate those, once it
exists to read across every bounded context anyway.

"Duplicado probable" is also NOT a rule here — that surface is
CustomerDuplicateCandidate's own dedicated, actionable workflow (this
phase, ``duplicate_use_cases.py``), not re-flagged as a second, competing
mechanism with a different resolution path.
"""

from __future__ import annotations

import re

from backend.domain.customers.enums import DataQualityRuleCode
from backend.domain.customers.exceptions import InvalidEmailAddressError, InvalidPhoneNumberError
from backend.domain.customers.value_objects.email_address import EmailAddress
from backend.domain.customers.value_objects.phone_number import PhoneNumber

_RFC_SHAPE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$")


class CustomerDataQualityService:
    def evaluate(
        self, *, display_name: str, phone_e164: str | None, email: str | None,
        tax_identifier: str | None, has_address: bool,
    ) -> list[tuple[DataQualityRuleCode, str]]:
        """Returns (rule_code, description) pairs for every rule this
        customer currently violates. Never raises — this is a detector, not
        a validator; malformed input is exactly what it's looking for."""
        issues: list[tuple[DataQualityRuleCode, str]] = []

        if not display_name or len(display_name.strip().split()) < 2:
            issues.append((DataQualityRuleCode.INCOMPLETE_NAME,
                           "El nombre no tiene al menos nombre y apellido"))

        if phone_e164:
            try:
                PhoneNumber(phone_e164)
            except InvalidPhoneNumberError:
                issues.append((DataQualityRuleCode.INVALID_PHONE,
                               f"Teléfono no está en formato E.164: {phone_e164!r}"))

        if email:
            try:
                EmailAddress(email)
            except InvalidEmailAddressError:
                issues.append((DataQualityRuleCode.INVALID_EMAIL,
                               f"Correo con formato inválido: {email!r}"))

        if tax_identifier and not _RFC_SHAPE.match(tax_identifier.strip().upper()):
            issues.append((DataQualityRuleCode.INVALID_TAX_ID,
                           f"RFC con formato inválido: {tax_identifier!r}"))

        if not has_address:
            issues.append((DataQualityRuleCode.INCOMPLETE_ADDRESS,
                           "El cliente no tiene ninguna dirección registrada"))

        return issues
