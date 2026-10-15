"""Signed release manifests — authentication before anything else.

The SHA-256 inside a manifest only proves the downloaded package matches the
manifest; it proves nothing about who wrote the manifest. So the manifest is
signed (Ed25519) by the release pipeline and verified here against public
keys EMBEDDED in the application (`trusted_keys.py`). Nothing in the payload —
version, URL, hash — is looked at until a signature from a trusted, non-revoked
key verifies over the exact canonical bytes.

Envelope `spj-signed-manifest/1`:

    {
      "format": "spj-signed-manifest/1",
      "payload": { ...spj-release/1, see domain/release_manifest.py... },
      "signatures": [
        {"key_id": "spj-release-2026a", "algorithm": "ed25519", "signature": "<base64>"}
      ]
    }

Signed bytes = `canonical_payload_bytes(payload)`: UTF-8 JSON with sorted
keys, no insignificant whitespace. Several signatures may be present while a
key is being rotated; one valid signature from a trusted key is enough.
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from backend.domain.software_distribution.release_manifest import ReleaseManifest

ENVELOPE_FORMAT = "spj-signed-manifest/1"
SIGNATURE_ALGORITHM = "ed25519"
#: A manifest is a few kilobytes; anything bigger is not a manifest.
MAX_MANIFEST_BYTES = 256 * 1024


class ManifestSignatureError(ValueError):
    """The manifest is not signed by a trusted key — treat as tampered."""


class ManifestFormatError(ValueError):
    """The bytes are not a signed-manifest envelope."""


def canonical_payload_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


@dataclass(frozen=True)
class TrustedKey:
    key_id: str
    public_key_b64: str
    revoked: bool = False
    note: str = ""

    def public_key(self) -> Ed25519PublicKey:
        return Ed25519PublicKey.from_public_bytes(base64.b64decode(self.public_key_b64))


class TrustedKeyring:
    def __init__(self, keys: Iterable[TrustedKey]) -> None:
        self._keys = {key.key_id: key for key in keys}

    @property
    def is_empty(self) -> bool:
        return not any(not key.revoked for key in self._keys.values())

    @property
    def key_ids(self) -> tuple[str, ...]:
        return tuple(sorted(k for k, v in self._keys.items() if not v.revoked))

    def verify(self, message: bytes, signatures: Iterable[Mapping[str, Any]]) -> str:
        """Return the key id that verified `message`, or raise."""
        if self.is_empty:
            raise ManifestSignatureError(
                "Esta compilación no tiene ninguna clave de firma de confianza; no se "
                "pueden aceptar actualizaciones. Consulte el manual de publicación.")
        reasons: list[str] = []
        for entry in signatures:
            key_id = str(entry.get("key_id", ""))
            key = self._keys.get(key_id)
            if key is None:
                reasons.append(f"clave desconocida {key_id!r}")
                continue
            if key.revoked:
                reasons.append(f"clave revocada {key_id!r}")
                continue
            if entry.get("algorithm") != SIGNATURE_ALGORITHM:
                reasons.append(f"algoritmo no soportado en {key_id!r}")
                continue
            try:
                signature = base64.b64decode(str(entry.get("signature", "")), validate=True)
                key.public_key().verify(signature, message)
            except (InvalidSignature, binascii.Error, ValueError):
                reasons.append(f"firma inválida con {key_id!r}")
                continue
            return key_id
        raise ManifestSignatureError(
            "El manifiesto no tiene una firma válida de una clave de confianza ("
            + ("; ".join(reasons) or "sin firmas") + "). Se descarta como alterado.")


@dataclass(frozen=True)
class AuthenticatedManifest:
    manifest: ReleaseManifest
    key_id: str
    payload_sha256: str
    raw: bytes


class SignedManifestReader:
    def __init__(self, keyring: TrustedKeyring) -> None:
        self._keyring = keyring

    def read(self, raw: bytes) -> AuthenticatedManifest:
        if len(raw) > MAX_MANIFEST_BYTES:
            raise ManifestFormatError("El manifiesto excede el tamaño máximo permitido.")
        try:
            envelope = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ManifestFormatError(f"El manifiesto no es JSON válido: {exc}") from exc
        if not isinstance(envelope, dict) or envelope.get("format") != ENVELOPE_FORMAT:
            raise ManifestFormatError("El archivo no es un manifiesto firmado de SPJ.")
        payload = envelope.get("payload")
        signatures = envelope.get("signatures")
        if not isinstance(payload, dict) or not isinstance(signatures, list):
            raise ManifestFormatError("Manifiesto firmado incompleto.")
        message = canonical_payload_bytes(payload)
        key_id = self._keyring.verify(message, [s for s in signatures if isinstance(s, dict)])
        # Only now, authenticated, is the payload interpreted.
        manifest = ReleaseManifest.from_payload(payload)
        return AuthenticatedManifest(manifest=manifest, key_id=key_id,
                                     payload_sha256=hashlib.sha256(message).hexdigest(), raw=raw)


class ManifestSigner:
    """Release tooling side (`scripts/release/sign_manifest.py`). The private
    key never ships with the application."""

    def __init__(self, private_key: Ed25519PrivateKey, key_id: str) -> None:
        self._key = private_key
        self._key_id = key_id

    @staticmethod
    def public_key_b64(private_key: Ed25519PrivateKey) -> str:
        from cryptography.hazmat.primitives import serialization

        raw = private_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        return base64.b64encode(raw).decode("ascii")

    def sign(self, payload: Mapping[str, Any], *,
             existing_signatures: Iterable[Mapping[str, Any]] = ()) -> dict[str, Any]:
        # Validate before signing: never sign a payload the client would reject.
        ReleaseManifest.from_payload(payload)
        signature = self._key.sign(canonical_payload_bytes(payload))
        signatures = [dict(s) for s in existing_signatures if s.get("key_id") != self._key_id]
        signatures.append({"key_id": self._key_id, "algorithm": SIGNATURE_ALGORITHM,
                           "signature": base64.b64encode(signature).decode("ascii")})
        return {"format": ENVELOPE_FORMAT, "payload": dict(payload), "signatures": signatures}
