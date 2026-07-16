"""PostingReference value object — canonical link from an entry to its source."""

from __future__ import annotations

from dataclasses import dataclass

from backend.domain.finance.enums import PostingPurpose
from backend.domain.finance.exceptions import FinanceDomainError


@dataclass(frozen=True, slots=True)
class PostingReference:
    """Identifies the single economic effect a journal entry recognizes.

    ``(source_module, source_document_id, posting_purpose)`` is the idempotency
    key: the same effect of the same source document must never post twice.
    """

    source_module: str
    source_document_id: str
    posting_purpose: PostingPurpose
    operation_id: str

    def __post_init__(self) -> None:
        for field_name in ("source_module", "source_document_id", "operation_id"):
            value = getattr(self, field_name)
            if not value or not str(value).strip():
                raise FinanceDomainError(f"PostingReference.{field_name} is required")
        if not isinstance(self.posting_purpose, PostingPurpose):
            raise FinanceDomainError("posting_purpose must be a PostingPurpose")

    def idempotency_key(self) -> tuple[str, str, str]:
        return (self.source_module, self.source_document_id, self.posting_purpose.value)
