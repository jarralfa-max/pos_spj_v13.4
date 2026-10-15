"""HTTPS download of manifests and installer packages, verified before use.

Replaces `urlretrieve(manifest.package_url, destination)`, which accepted any
scheme and host, wrote straight to the final name and never compared the
hash. Rules now:

* HTTPS only, certificate verified by the system trust store, host in the
  station's allow-list — checked again on EVERY redirect hop;
* a timeout on connect/read and a hard size cap (the manifest's declared size;
  a server that sends more is cut off, not trusted);
* the bytes go to `<name>.part` and SHA-256 is computed while streaming; only
  when size AND hash match is the file renamed to its final name;
* a file name that could escape the downloads folder is impossible: it comes
  from the validated manifest (`ReleaseArtifact.file_name`), never from the
  URL or a `Content-Disposition` header.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import ssl
from typing import Callable, Protocol
from urllib.error import URLError
from urllib.parse import urlsplit
import urllib.request

from backend.domain.software_distribution.release_manifest import ReleaseArtifact
from backend.infrastructure.updater.package_integrity import (
    PackageIntegrityError,
    verify_file,
)
from backend.infrastructure.updater.update_manifest import MAX_MANIFEST_BYTES

CHUNK_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 30.0

ProgressCallback = Callable[[int, int], None]
CancelCheck = Callable[[], bool]


class PackageDownloadError(RuntimeError):
    pass


class DownloadCancelledError(PackageDownloadError):
    pass


class UrlOpener(Protocol):
    def open(self, request: urllib.request.Request, timeout: float): ...


class _AllowListRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self._allowed = allowed_hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _require_allowed(newurl, self._allowed)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def default_opener(allowed_hosts: frozenset[str]) -> urllib.request.OpenerDirector:
    context = ssl.create_default_context()
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        _AllowListRedirectHandler(allowed_hosts),
    )


def _require_allowed(url: str, allowed_hosts: frozenset[str]) -> None:
    parts = urlsplit(url)
    if parts.scheme != "https":
        raise PackageDownloadError(f"Sólo se permiten descargas HTTPS (se recibió {parts.scheme!r}).")
    if (parts.hostname or "").lower() not in allowed_hosts:
        raise PackageDownloadError(f"Servidor no autorizado: {parts.hostname!r}.")


def verify_package_file(path: Path, artifact: ReleaseArtifact) -> None:
    """Size + SHA-256 of a local package (downloaded or offline media)."""
    try:
        verify_file(path, artifact.size, artifact.sha256)
    except PackageIntegrityError as exc:
        raise PackageDownloadError(str(exc)) from exc


class UpdateDownloader:
    def __init__(
        self, downloads_dir: Path, *, allowed_hosts: frozenset[str],
        opener: UrlOpener | None = None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._dir = Path(downloads_dir)
        self._allowed = frozenset(h.lower() for h in allowed_hosts)
        self._opener = opener or default_opener(self._allowed)
        self._timeout = timeout_seconds

    def fetch_manifest(self, url: str) -> bytes:
        _require_allowed(url, self._allowed)
        body, _ = self._read(url, limit=MAX_MANIFEST_BYTES, sink=None)
        return body

    def target_path(self, artifact: ReleaseArtifact) -> Path:
        return self._dir / artifact.file_name

    def download(
        self, artifact: ReleaseArtifact, *, progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> Path:
        _require_allowed(artifact.url, self._allowed)
        self._dir.mkdir(parents=True, exist_ok=True)
        final = self.target_path(artifact)
        if final.exists():
            try:
                verify_package_file(final, artifact)
                if progress:
                    progress(artifact.size, artifact.size)
                return final
            except PackageDownloadError:
                final.unlink(missing_ok=True)  # stale or tampered: download again
        partial = final.with_name(final.name + ".part")
        partial.unlink(missing_ok=True)
        try:
            with open(partial, "wb") as sink:
                _, digest = self._read(artifact.url, limit=artifact.size, sink=sink,
                                       progress=progress, cancelled=cancelled,
                                       expected=artifact.size)
            size = partial.stat().st_size
            if size != artifact.size:
                raise PackageDownloadError(
                    f"Descarga incompleta: {size} de {artifact.size} bytes.")
            if digest != artifact.sha256:
                raise PackageDownloadError(
                    "El hash SHA-256 del paquete descargado no coincide con el manifiesto; "
                    "se descartó.")
            os.replace(partial, final)
            return final
        except BaseException:
            partial.unlink(missing_ok=True)
            raise

    def _read(self, url, *, limit, sink, progress=None, cancelled=None, expected=None):
        request = urllib.request.Request(url, headers={"User-Agent": "SPJ-Updater"})
        digest = hashlib.sha256()
        body = bytearray()
        received = 0
        try:
            response = self._opener.open(request, timeout=self._timeout)
        except (URLError, OSError, ValueError) as exc:
            raise PackageDownloadError(f"No se pudo conectar con {urlsplit(url).hostname}: {exc}") from exc
        try:
            final_url = getattr(response, "geturl", lambda: url)()
            _require_allowed(final_url, self._allowed)
            declared = (getattr(response, "headers", None) or {}).get("Content-Length")
            if declared is not None and str(declared).isdigit() and int(declared) > limit:
                raise PackageDownloadError(
                    f"El servidor anuncia {declared} bytes; el máximo permitido es {limit}.")
            while True:
                if cancelled is not None and cancelled():
                    raise DownloadCancelledError("Descarga cancelada.")
                try:
                    chunk = response.read(CHUNK_BYTES)
                except (URLError, OSError) as exc:
                    raise PackageDownloadError(f"La descarga se interrumpió: {exc}") from exc
                if not chunk:
                    break
                received += len(chunk)
                if received > limit:
                    raise PackageDownloadError(
                        f"El servidor envió más de {limit} bytes; se descartó la descarga.")
                digest.update(chunk)
                if sink is None:
                    body.extend(chunk)
                else:
                    sink.write(chunk)
                if progress is not None and expected:
                    progress(received, expected)
        finally:
            close = getattr(response, "close", None)
            if close:
                close()
        return bytes(body), digest.hexdigest()
