"""Shared builders for the software-distribution tests: a throw-away Ed25519
release key, signed manifests and a tiny fake HTTPS opener."""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.infrastructure.updater.update_manifest import (
    ManifestSigner,
    SignedManifestReader,
    TrustedKey,
    TrustedKeyring,
)

HOST = "updates.example.test"


def new_key(key_id: str = "test-2026a"):
    private = Ed25519PrivateKey.generate()
    trusted = TrustedKey(key_id, ManifestSigner.public_key_b64(private))
    return private, trusted


def reader_for(*trusted: TrustedKey) -> SignedManifestReader:
    return SignedManifestReader(TrustedKeyring(trusted))


def release_payload(*, version="13.5.0", package: bytes = b"installer-bytes", channel="stable",
                    arch="x64", minimum="13.4.0", requires=300, migrates=400, host=HOST,
                    rollout=None, **extra) -> dict:
    name = f"SPJ-Setup-{version}-{arch}.exe"
    payload = {
        "format": "spj-release/1", "product": "spj-erp-pos", "version": version,
        "channel": channel, "published_at": "2026-10-14T00:00:00Z",
        "platform": {"os": "windows", "arch": arch},
        "minimum_installed_version": minimum,
        "database_schema": {"requires_at_least": requires, "migrates_to": migrates},
        "artifact": {"kind": "inno-setup", "file_name": name,
                     "url": f"https://{host}/{channel}/{name}", "size": len(package),
                     "sha256": hashlib.sha256(package).hexdigest()},
        "release_notes": "Notas de prueba", "mandatory": False, "mandatory_deadline": None,
        "rollout": rollout or {"percent": 100, "branch_ids": [], "workstation_ids": []},
    }
    payload.update(extra)
    return payload


def signed_bytes(private, key_id: str, payload: dict) -> bytes:
    envelope = ManifestSigner(private, key_id).sign(payload)
    return json.dumps(envelope).encode("utf-8")


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, url: str, *, content_length: int | None = None,
                 chunks: int | None = None) -> None:
        super().__init__(body)
        self._url = url
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def geturl(self) -> str:
        return self._url


class FakeOpener:
    """Maps URL → (body, final_url, content_length)."""

    def __init__(self, routes: dict) -> None:
        self.routes = routes
        self.requests: list[str] = []

    def open(self, request, timeout):
        url = request.full_url
        self.requests.append(url)
        if url not in self.routes:
            raise OSError(f"404 {url}")
        body, final_url, declared = self.routes[url]
        return FakeResponse(body, final_url or url, content_length=declared)


def make_wal_database(path: Path, rows: int = 25, *, schema_versions=("000", "337")) -> sqlite3.Connection:
    """A WAL database whose last transactions are still in -wal (the returned
    connection stays open so nothing is checkpointed)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA wal_autocheckpoint=0")
    connection.execute("CREATE TABLE IF NOT EXISTS sales (id TEXT PRIMARY KEY, total REAL)")
    connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY)")
    connection.executemany("INSERT OR IGNORE INTO schema_migrations VALUES (?)",
                           [(v,) for v in schema_versions])
    connection.executemany("INSERT INTO sales VALUES (?, ?)",
                           [(f"s-{i}", float(i)) for i in range(rows)])
    connection.commit()
    return connection


def count_sales(path: Path) -> int:
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    finally:
        connection.close()
