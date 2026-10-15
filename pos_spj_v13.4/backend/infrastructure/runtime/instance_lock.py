"""Cross-process exclusive lock on a file — "who has this database open".

The desktop holds it for its whole life; the external updater and the legacy
database relocation take it before touching the database. It replaces the
`QLocalServer` single-instance probe, which only another Qt process could see:
the updater runs without the application and must know whether a till is
still open.

The operating system releases the lock when the holding process dies, so a
crash never leaves a stale lock behind (unlike a "pid file").
"""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time


class InstanceLockError(RuntimeError):
    pass


class InstanceLock:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._handle = None

    @property
    def path(self) -> Path:
        return self._path

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self, *, timeout_seconds: float = 0.0, poll_seconds: float = 0.25) -> bool:
        """True when acquired. Waits up to `timeout_seconds` for the holder."""
        if self._handle is not None:
            return True
        self._path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + max(timeout_seconds, 0.0)
        while True:
            handle = open(self._path, "a+b")
            try:
                _lock(handle)
            except OSError:
                handle.close()
                if time.monotonic() >= deadline:
                    return False
                time.sleep(poll_seconds)
                continue
            try:
                handle.seek(0)
                handle.truncate()
                handle.write(f"{os.getpid()}\n".encode("ascii"))
                handle.flush()
            except OSError:
                # On Windows the locked byte range blocks even our own write
                # through another path; the pid is informational only.
                pass
            self._handle = handle
            return True

    def release(self) -> None:
        handle, self._handle = self._handle, None
        if handle is None:
            return
        try:
            _unlock(handle)
        finally:
            handle.close()

    def __enter__(self) -> "InstanceLock":
        if not self.acquire():
            raise InstanceLockError(f"Otro proceso tiene abierta la base ({self._path}).")
        return self

    def __exit__(self, *exc) -> None:
        self.release()


if sys.platform == "win32":
    import msvcrt

    def _lock(handle) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock(handle) -> None:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _lock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
