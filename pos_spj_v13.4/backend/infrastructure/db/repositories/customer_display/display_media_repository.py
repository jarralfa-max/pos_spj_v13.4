"""Registro de los archivos de media de la pantalla del cliente."""

from __future__ import annotations

from backend.domain.customer_display.entities.display_media import DisplayMedia
from backend.infrastructure.db.repositories.customer_display.base import (
    CustomerDisplayRepositoryBase,
)

_COLS = ("id, media_type, original_name, stored_name, size_bytes, sha256,"
         " created_by_user_id, created_at")


class SqliteDisplayMediaRepository(CustomerDisplayRepositoryBase):
    def save(self, media: DisplayMedia) -> None:
        self._execute(
            f"INSERT INTO display_media ({_COLS}) VALUES (?,?,?,?,?,?,?,?)",
            (media.id, media.media_type, media.original_name, media.stored_name,
             media.size_bytes, media.sha256, media.created_by_user_id, media.created_at))

    def get(self, media_id: str) -> DisplayMedia | None:
        row = self._query_one(f"SELECT {_COLS} FROM display_media WHERE id=?", (str(media_id),))
        return DisplayMedia(**row) if row else None

    def get_by_hash(self, sha256: str) -> DisplayMedia | None:
        row = self._query_one(f"SELECT {_COLS} FROM display_media WHERE sha256=?", (sha256,))
        return DisplayMedia(**row) if row else None
