"""ConnectionCloser — SHELL-15.

The pluggable "close every open database connection" port
`ConnectionsShutdownStep` calls through — the real pool lives in legacy
`core/db/` and is due to migrate to `infrastructure/persistence/` per
CLAUDE.md's transition notes; this Protocol is the seam a real adapter
around that pool (or its eventual replacement) implements, same
declare-the-port discipline as `OutboxFlusher` above.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ConnectionCloser(Protocol):
    def close_all(self) -> int: ...
