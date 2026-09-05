"""View-models for the Activos desktop workspace (ASSET-16).

``AssetsCapabilities`` gates entire ``assets_routes.py`` nav GROUPS (one flag
per §8 sidebar section), not one flag per individual route — same
deliberately coarse shape as `customers_crm`'s `CustomerCrmCapabilities`
(ASSET-16 is UI *foundations*: routes/sidebar/header, not all ~33 pages).
A later phase building a specific page can introduce its own finer-grained
capability without reshaping this dataclass's existing fields.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssetsCapabilities:
    module_view: bool = False
    activos: bool = False
    mantenimiento: bool = False
    costos: bool = False
    movimientos: bool = False
    control_fisico: bool = False
    documentacion: bool = False
    bajas: bool = False
    control: bool = False
