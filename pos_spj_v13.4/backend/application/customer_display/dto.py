"""DTOs for the Customer Display bounded context's own application layer
— SET-18 cutover.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedAdDTO:
    placement_id: str
    campaign_id: str
    content_id: str
    title: str
    content_type: str
    body: str
    duration_seconds: int
