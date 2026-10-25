"""Presenter de códigos de barras y perfiles de UN producto (PROD-22, §17-20).

Dos piezas del expediente del producto cuyo backend existía (PROD-7 y PROD-8:
casos de uso con validación GS1, unicidad de códigos activos y auditoría) sin
ninguna pantalla que las alcanzara:

* códigos de barras / PLU / código de báscula, y códigos alternos;
* vida útil, perfil de calidad y perfil logístico (cadena de frío).

Van como acciones del producto, no como secciones del menú: son datos de UN
producto (regla del usuario: el menú no repite el expediente).
"""

from __future__ import annotations

import logging

from backend.application.products.permissions import ProductPermissions

logger = logging.getLogger("spj.products.codes_profiles_presenter")

BARCODE_TYPE_ES = {
    "EAN": "EAN-13", "UPC": "UPC-A", "GTIN": "GTIN", "PLU": "PLU",
    "SCALE_BARCODE": "Código de báscula", "INTERNAL_SKU": "Código interno",
    "QR": "QR", "SUPPLIER_CODE": "Código de proveedor", "LOT_LABEL": "Etiqueta de lote",
    "CARCASS_TAG": "Arete / etiqueta de canal", "CUSTOM": "Otro",
}
STORAGE_CONDITION_ES = {"AMBIENT": "Ambiente", "CHILLED": "Refrigerado",
                        "FROZEN": "Congelado"}


class ProductCodesProfilesPresenter:
    def __init__(self, *, read_factory, write_factory=None, has_permission=None,
                 session=None) -> None:
        self._read = read_factory
        self._write = write_factory
        self._has = has_permission
        self._session = session

    def _allowed(self, code: str) -> bool:
        if self._write is None:
            return False
        return True if self._has is None else bool(self._has(code))

    @property
    def can_manage_barcodes(self) -> bool:
        return self._allowed(ProductPermissions.BARCODES_MANAGE)

    @property
    def can_manage_alternate_codes(self) -> bool:
        return self._allowed(ProductPermissions.ALTERNATE_CODES_MANAGE)

    @property
    def can_edit_profiles(self) -> bool:
        return self._allowed(ProductPermissions.EDIT)

    # ── lecturas ───────────────────────────────────────────────────────────
    def barcodes(self, product_id: str) -> list[dict]:
        barcodes_qs, _profiles_qs = self._read()
        return barcodes_qs.list_barcodes(product_id)

    def alternate_codes(self, product_id: str) -> list[dict]:
        barcodes_qs, _profiles_qs = self._read()
        return barcodes_qs.list_alternate_codes(product_id)

    def profiles(self, product_id: str) -> dict:
        _barcodes_qs, profiles_qs = self._read()
        return {"shelf_life": profiles_qs.shelf_life(product_id),
                "quality": profiles_qs.quality(product_id),
                "logistics": profiles_qs.logistics(product_id)}

    # ── códigos ────────────────────────────────────────────────────────────
    def assign_barcode(self, *, product_id: str, value: str, barcode_type: str,
                       is_primary: bool = False) -> tuple[bool, str]:
        from backend.application.products.commands.product_barcode_commands import (
            AssignBarcodeCommand,
        )
        return self._run("assign_barcode", lambda op, user: AssignBarcodeCommand(
            operation_id=op, product_id=product_id, value=value,
            barcode_type=barcode_type, is_primary=is_primary, user_id=user))

    def preview_internal_barcode(self) -> str:
        """EAN-13 interno sugerido para quien no trae código de fabricante."""
        barcodes_qs, _profiles_qs = self._read()
        try:
            return barcodes_qs.preview_internal_barcode()
        except Exception:  # noqa: BLE001 — sin sugerencia; se captura a mano
            return ""

    def set_barcode_active(self, barcode_id: str, active: bool) -> tuple[bool, str]:
        from backend.application.products.commands.product_barcode_commands import (
            SetBarcodeActiveCommand,
        )
        return self._run("set_barcode_active", lambda op, user: SetBarcodeActiveCommand(
            operation_id=op, barcode_id=barcode_id, active=active, user_id=user))

    def add_alternate_code(self, *, product_id: str, code: str,
                           code_type: str = "SUPPLIER_CODE") -> tuple[bool, str]:
        from backend.application.products.commands.product_barcode_commands import (
            AddAlternateCodeCommand,
        )
        return self._run("add_alternate_code", lambda op, user: AddAlternateCodeCommand(
            operation_id=op, product_id=product_id, code=code, code_type=code_type,
            user_id=user))

    # ── perfiles ───────────────────────────────────────────────────────────
    def save_shelf_life(self, *, product_id: str, **fields) -> tuple[bool, str]:
        from backend.application.products.commands.product_profile_commands import (
            SetShelfLifeProfileCommand,
        )
        return self._run("shelf_life", lambda op, user: SetShelfLifeProfileCommand(
            operation_id=op, product_id=product_id, user_id=user, **fields))

    def save_quality(self, *, product_id: str, **fields) -> tuple[bool, str]:
        from backend.application.products.commands.product_profile_commands import (
            SetQualityProfileCommand,
        )
        return self._run("quality", lambda op, user: SetQualityProfileCommand(
            operation_id=op, product_id=product_id, user_id=user, **fields))

    def save_logistics(self, *, product_id: str, **fields) -> tuple[bool, str]:
        from backend.application.products.commands.product_profile_commands import (
            SetLogisticsProfileCommand,
        )
        return self._run("logistics", lambda op, user: SetLogisticsProfileCommand(
            operation_id=op, product_id=product_id, user_id=user, **fields))

    def _run(self, action: str, build) -> tuple[bool, str]:
        if self._write is None:
            return False, "Sin permisos para modificar este producto"
        from backend.shared.ids import new_uuid
        user_id = getattr(self._session, "user_id", None)
        try:
            result = self._write()[action].execute(build(new_uuid(), user_id))
        except Exception as exc:  # noqa: BLE001 — se muestra en la pantalla
            logger.exception("Códigos/perfiles: %s falló", action)
            return False, f"Error: {exc}"
        return bool(result.success), result.message
