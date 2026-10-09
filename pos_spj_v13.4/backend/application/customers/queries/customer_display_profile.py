"""Expediente para mostrar, con los datos sensibles enmascarados (§75, CRM-43).

``CustomerProfileQueryService.get_profile`` devuelve el expediente en claro
(lo usan casos de uso y la fusión). Las PANTALLAS reciben esta versión: el
teléfono, el correo, el RFC y la calle se enmascaran según el permiso de
quien mira — nunca lo decide la pantalla.

* ``CLIENTES.sensible.ver``  → VISIBLE (dueño, administrador, gerente).
* ``CLIENTES.contacto.ver``  → PARCIAL (últimos 4: el cajero reconoce al
  cliente sin ver el dato completo).
* nada de lo anterior        → OCULTO (solo lectura).

``visibility`` viaja en el resultado para que un formulario de edición sepa
que NO debe precargar un valor enmascarado (guardarlo lo destruiría).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend.application.customers.permissions import CustomerPermissions
from backend.application.customers.queries.customer_profile_query_service import (
    CustomerProfile,
)
from backend.domain.customers.value_objects.field_visibility import FieldVisibility, mask


@dataclass(frozen=True)
class DisplayCustomerProfile:
    profile: CustomerProfile
    visibility: FieldVisibility


def resolve_visibility(authorization, actor_user_id: str) -> FieldVisibility:
    if authorization.has_permission(actor_user_id, CustomerPermissions.SENSITIVE_DATA_VIEW):
        return FieldVisibility.VISIBLE
    if authorization.has_permission(actor_user_id, CustomerPermissions.CONTACT_VIEW):
        return FieldVisibility.PARTIALLY_VISIBLE
    return FieldVisibility.MASKED


def _m(value, visibility: FieldVisibility):
    if value in (None, ""):
        return value
    return mask(str(value), visibility)


def mask_profile(profile: CustomerProfile, visibility: FieldVisibility) -> CustomerProfile:
    if visibility == FieldVisibility.VISIBLE:
        return profile
    contacts = [replace(c, phone_e164=_m(c.phone_e164, visibility),
                        email=_m(c.email, visibility)) for c in profile.contacts]
    addresses = [replace(a, street=_m(a.street, visibility),
                         external_number=_m(a.external_number, visibility),
                         internal_number=_m(a.internal_number, visibility),
                         references=_m(a.references, visibility),
                         latitude=None, longitude=None) for a in profile.addresses]
    tax = profile.tax_profile
    if tax is not None:
        tax = replace(tax, tax_identifier=_m(tax.tax_identifier, visibility),
                      billing_email=_m(tax.billing_email, visibility))
    return replace(profile, contacts=contacts, addresses=addresses, tax_profile=tax)


def display_profile(service, authorization, customer_id: str, context) -> DisplayCustomerProfile:
    visibility = resolve_visibility(authorization, context.user_id)
    profile = service.get_profile(customer_id, context)
    return DisplayCustomerProfile(mask_profile(profile, visibility), visibility)
