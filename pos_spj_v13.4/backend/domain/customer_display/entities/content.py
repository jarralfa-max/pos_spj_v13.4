"""Content — SET-18 "Content": one reusable piece of advertising/idle-
screen material (image, video, text message, or HTML) a `ContentCampaign`
schedules and an `AdvertisingSlot` eventually shows. Mostly-static
identity/metadata — mirrors
`backend.domain.document_output.entities.document_template.DocumentTemplate`'s
role relative to its versions, except SET-18 doesn't call for a
versioned-content history the way Document Output's templates do, so
`body` is edited in place rather than chained through new versions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from backend.domain.customer_display.enums import ContentType
from backend.domain.customer_display.exceptions import CustomerDisplayInvalidValueError
from backend.shared.ids import new_uuid


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class Content:
    id: str
    title: str
    content_type: ContentType
    body: str
    duration_seconds: int = 10
    active: bool = True
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)

    @classmethod
    def create(
        cls, *, title: str, content_type: ContentType, body: str, duration_seconds: int = 10,
    ) -> "Content":
        if not title.strip():
            raise CustomerDisplayInvalidValueError("title es obligatorio")
        if not body.strip():
            raise CustomerDisplayInvalidValueError("body es obligatorio")
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds <= 0:
            raise CustomerDisplayInvalidValueError(
                f"duration_seconds debe ser un entero > 0, recibido {duration_seconds!r}"
            )
        return cls(
            id=new_uuid(), title=title.strip(), content_type=content_type, body=body.strip(),
            duration_seconds=duration_seconds,
        )

    def _touch(self) -> None:
        self.updated_at = _utcnow()

    def update_details(self, *, title: str, body: str, duration_seconds: int = 10) -> None:
        if not title.strip():
            raise CustomerDisplayInvalidValueError("title es obligatorio")
        if not body.strip():
            raise CustomerDisplayInvalidValueError("body es obligatorio")
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds <= 0:
            raise CustomerDisplayInvalidValueError(
                f"duration_seconds debe ser un entero > 0, recibido {duration_seconds!r}"
            )
        self.title = title.strip()
        self.body = body.strip()
        self.duration_seconds = duration_seconds
        self._touch()

    def activate(self) -> None:
        self.active = True
        self._touch()

    def deactivate(self) -> None:
        self.active = False
        self._touch()
