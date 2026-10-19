"""Logo de la empresa y de cada sucursal para los documentos impresos
(comparativa de tickets main ↔ ERP, 2026-10-16).

Antes `Configuración → Empresa` pedía teclear el UUID de «un asset ya
registrado en otro sistema», sistema que no existía: el ticket nunca tuvo logo.
Ahora se carga una imagen, se ve antes/después de quitar el fondo (con la
tolerancia ajustable o conservándolo) y se asigna a la empresa o a una sucursal
(decisión del usuario: empresa + sucursal opcional; sin el suyo, la sucursal
hereda el de la empresa).

El ORIGINAL nunca se destruye: re-procesar parte siempre de él.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.infrastructure.media.branding_asset_storage import (
    BrandingAssetError,
    BrandingAssetStorage,
)
from backend.shared.ids import new_uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class LogoPreview:
    original_path: str
    print_path: str


@dataclass(frozen=True)
class BrandingAsset:
    id: str
    original_path: str
    print_path: str
    background_removed: bool
    tolerance: float | None


def _tolerance(value) -> float | None:
    """0 o vacío = automática (el removedor la calcula del fondo)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if not 5 <= number <= 120:
        raise BrandingAssetError("La tolerancia va de 5 a 120 (0 = automática)")
    return number


class PreviewLogoUseCase:
    """Antes/después sin guardar nada en la biblioteca."""

    def __init__(self, storage: BrandingAssetStorage | None = None) -> None:
        self._storage = storage or BrandingAssetStorage()

    def execute(self, *, source_path: str, remove_background: bool, tolerance=None,
                preview_dir: str) -> LogoPreview:
        import os
        import shutil

        os.makedirs(preview_dir, exist_ok=True)
        original = os.path.join(preview_dir, "original.png")
        shutil.copyfile(source_path, original) if source_path.lower().endswith(".png") \
            else _save_png(source_path, original)
        printed = self._storage.derive_print_version(
            original, remove_background=remove_background, tolerance=_tolerance(tolerance),
            target_path=os.path.join(preview_dir, "impresion.png"))
        return LogoPreview(original, printed)


def _save_png(source: str, target: str) -> None:
    from PIL import Image, UnidentifiedImageError
    try:
        with Image.open(source) as image:
            image.convert("RGBA").save(target, "PNG")
    except (UnidentifiedImageError, OSError) as exc:
        raise BrandingAssetError("El archivo no es una imagen válida") from exc


class ImportLogoUseCase:
    def __init__(self, connection, storage: BrandingAssetStorage | None = None) -> None:
        self._conn = connection
        self._storage = storage or BrandingAssetStorage()

    def execute(self, *, source_path: str, remove_background: bool, tolerance=None,
                actor_user_id: str = "") -> BrandingAsset:
        tol = _tolerance(tolerance)
        original, (width, height) = self._storage.import_original(source_path)
        printed = self._storage.derive_print_version(
            original, remove_background=remove_background, tolerance=tol)
        asset = BrandingAsset(new_uuid(), original, printed, bool(remove_background), tol)
        self._conn.execute(
            "INSERT INTO branding_assets (id, kind, original_path, print_path, background_removed,"
            " tolerance, width_px, height_px, created_by_user_id, created_at)"
            " VALUES (?, 'LOGO', ?, ?, ?, ?, ?, ?, ?, ?)",
            (asset.id, original, printed, int(asset.background_removed),
             None if tol is None else str(tol), width, height, actor_user_id or None, _now()))
        self._conn.commit()
        return asset


class SetCompanyLogoUseCase:
    """`None` quita el logo de la empresa."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def execute(self, *, asset_id: str | None) -> None:
        from backend.domain.settings.value_objects.asset_reference import AssetReference
        from backend.infrastructure.db.repositories.settings.company_profile_repository import (
            SqliteCompanyProfileRepository,
        )

        companies = SqliteCompanyProfileRepository(self._conn)
        profiles = companies.list_active()
        if not profiles:
            raise BrandingAssetError(
                "Primero captura los datos de la empresa (Configuración → Empresa y sucursales)")
        if asset_id:
            _require_asset(self._conn, asset_id)
        profile = profiles[0]
        profile.replace_logo(AssetReference.create(asset_id) if asset_id else None)
        companies.save(profile)
        self._conn.commit()


class SetBranchLogoUseCase:
    """`None` = la sucursal vuelve a heredar el logo de la empresa."""

    def __init__(self, connection) -> None:
        self._conn = connection

    def execute(self, *, branch_id: str, asset_id: str | None, actor_user_id: str = "") -> None:
        if asset_id:
            _require_asset(self._conn, asset_id)
            self._conn.execute(
                "INSERT INTO branch_branding (branch_id, logo_asset_id, updated_by_user_id,"
                " updated_at) VALUES (?,?,?,?) ON CONFLICT(branch_id) DO UPDATE SET"
                " logo_asset_id=excluded.logo_asset_id,"
                " updated_by_user_id=excluded.updated_by_user_id, updated_at=excluded.updated_at",
                (branch_id, asset_id, actor_user_id or None, _now()))
        else:
            self._conn.execute("DELETE FROM branch_branding WHERE branch_id=?", (branch_id,))
        self._conn.commit()


def _require_asset(conn, asset_id: str) -> None:
    if conn.execute("SELECT 1 FROM branding_assets WHERE id=?", (asset_id,)).fetchone() is None:
        raise BrandingAssetError("Ese logo no está en la biblioteca; vuelve a cargarlo")


__all__ = [
    "BrandingAsset", "BrandingAssetError", "ImportLogoUseCase", "LogoPreview",
    "PreviewLogoUseCase", "SetBranchLogoUseCase", "SetCompanyLogoUseCase",
]
