"""Sync transport contract (§57, INV-22).

The dispatcher is transport-agnostic: it hands an event payload to a
``SyncTransport`` and treats a raised ``SyncTransportError`` as a retryable
failure. Production wires a REST/queue transport; the in-memory one backs tests
and a fully-offline node (nothing leaves, everything stays queued for later).
"""

from __future__ import annotations

from typing import Protocol


class SyncTransportError(Exception):
    """Raised by a transport when an event could not be delivered (retryable)."""


class SyncTransport(Protocol):
    def send(self, event: dict) -> None: ...


class InMemoryTransport:
    """Collects delivered events; used in tests and single-node/offline setups."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, event: dict) -> None:
        self.sent.append(event)
