"""AssetDocument — invoices, manuals, photos, certificates, etc. (ASSET-9, §42-43).

``storage_reference`` is an opaque token from a DocumentStorageGateway (a
later infrastructure phase) — never a raw filesystem path stored directly
(§42 forbids that). Every file must carry MIME type, size and hash (§43).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.assets.enums import AssetDocumentType
from backend.domain.assets.exceptions import AssetDomainError
from backend.shared.ids import new_uuid

_MAX_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB, a sane default — configurable in a later phase.


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class AssetDocument:
    id: str
    asset_id: str
    document_type: AssetDocumentType
    storage_reference: str
    mime_type: str
    size_bytes: int
    file_hash: str
    uploaded_by: str
    operation_id: str
    description: str = ""
    uploaded_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(cls, asset_id: str, document_type: AssetDocumentType, storage_reference: str,
               mime_type: str, size_bytes: int, file_hash: str, uploaded_by: str,
               operation_id: str, *, description: str = "") -> "AssetDocument":
        if not asset_id:
            raise AssetDomainError("AssetDocument.asset_id is required")
        if not storage_reference:
            raise AssetDomainError("AssetDocument.storage_reference is required")
        if not mime_type:
            raise AssetDomainError("AssetDocument.mime_type is required")
        if size_bytes <= 0:
            raise AssetDomainError("AssetDocument.size_bytes must be positive")
        if size_bytes > _MAX_SIZE_BYTES:
            raise AssetDomainError(
                f"AssetDocument.size_bytes exceeds the maximum allowed ({_MAX_SIZE_BYTES})")
        if not file_hash:
            raise AssetDomainError("AssetDocument.file_hash is required")
        if not uploaded_by:
            raise AssetDomainError("AssetDocument.uploaded_by is required")
        return cls(
            id=new_uuid(), asset_id=asset_id, document_type=document_type,
            storage_reference=storage_reference, mime_type=mime_type, size_bytes=size_bytes,
            file_hash=file_hash, uploaded_by=uploaded_by, operation_id=operation_id,
            description=description,
        )
