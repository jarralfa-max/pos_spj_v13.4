"""View-models for the Clientes y CRM desktop workspace (CRM-14).

``CustomerCrmCapabilities`` gates entire ``customers_crm_routes.py`` nav
GROUPS, not one flag per individual route the way `cash_register`'s
``CashCapabilities`` does — deliberately coarser, because CRM-14 is UI
*foundations* (routes/sidebar/header/density/theme/icons), not the ~61
feature pages themselves. Each group's flag maps to that group's most
representative existing permission (see ``capability_resolver.py``); once a
later phase builds real pages for a group, that page can introduce its own
finer-grained capability the same way `cash_register` did, without
reshaping this dataclass's existing fields.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CustomerCrmCapabilities:
    module_view: bool = False
    clientes: bool = False
    prospectos: bool = False
    oportunidades: bool = False
    actividades: bool = False
    atencion: bool = False
    comercial: bool = False
    credito: bool = False
    segmentacion: bool = False
    comunicaciones: bool = False
    privacidad: bool = False
    control: bool = False
