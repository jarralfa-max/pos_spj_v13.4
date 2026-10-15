"""Size + SHA-256 of a package file — dependency-free on purpose: the external
updater (a small single-file executable) re-checks the staged installer with
this right before running it, without loading the cryptography stack."""
from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK_BYTES = 1024 * 1024


class PackageIntegrityError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(path: Path, size: int, sha256: str) -> None:
    path = Path(path)
    if not path.is_file():
        raise PackageIntegrityError(f"No existe el paquete {path}.")
    actual = path.stat().st_size
    if actual != size:
        raise PackageIntegrityError(
            f"El paquete mide {actual} bytes y el manifiesto declara {size}.")
    if file_sha256(path) != sha256.lower():
        raise PackageIntegrityError("El hash SHA-256 del paquete no coincide con el manifiesto.")
