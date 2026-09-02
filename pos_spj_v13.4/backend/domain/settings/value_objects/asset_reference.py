"""AssetReference — §15: "No almacenar logos como rutas arbitrarias.
Usar: AssetReference." A logo (or any other uploaded file this bounded
context points at) is referenced by the UUIDv7 id of an asset record
managed elsewhere, never by a raw filesystem path or URL string.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.shared.ids import validate_uuidv7


@dataclass(frozen=True, slots=True)
class AssetReference:
    asset_id: str

    @classmethod
    def create(cls, asset_id: str) -> "AssetReference":
        return cls(validate_uuidv7(asset_id))
