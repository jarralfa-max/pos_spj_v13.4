"""Signed manifests and verified downloads: anything altered, incomplete,
from another host or oversized is rejected before it is used."""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

from backend.infrastructure.updater.update_downloader import (
    DownloadCancelledError,
    PackageDownloadError,
    UpdateDownloader,
)
from backend.infrastructure.updater.update_manifest import (
    ManifestFormatError,
    ManifestSignatureError,
    ManifestSigner,
    TrustedKey,
    TrustedKeyring,
    SignedManifestReader,
)
from backend.domain.software_distribution.release_manifest import (
    ManifestValidationError,
    ReleaseManifest,
)

from ._helpers import HOST, FakeOpener, new_key, reader_for, release_payload, signed_bytes

PACKAGE = b"MZ" + b"\x00" * 4096 + b"spj installer"


@pytest.fixture()
def key():
    return new_key()


def test_valid_signature_is_accepted(key):
    private, trusted = key
    raw = signed_bytes(private, trusted.key_id, release_payload(package=PACKAGE))
    authenticated = reader_for(trusted).read(raw)
    assert authenticated.key_id == trusted.key_id
    assert str(authenticated.manifest.version) == "13.5.0"


@pytest.mark.parametrize("field, value", [
    ("version", "13.9.9"),
    ("channel", "pilot"),
    ("artifact", None),  # replaced below with a different URL/hash
])
def test_any_change_after_signing_breaks_the_signature(key, field, value):
    private, trusted = key
    envelope = json.loads(signed_bytes(private, trusted.key_id, release_payload(package=PACKAGE)))
    if field == "artifact":
        envelope["payload"]["artifact"]["sha256"] = hashlib.sha256(b"evil").hexdigest()
    else:
        envelope["payload"][field] = value
    with pytest.raises(ManifestSignatureError):
        reader_for(trusted).read(json.dumps(envelope).encode())


def test_unknown_revoked_and_missing_keys_are_rejected(key):
    private, trusted = key
    raw = signed_bytes(private, trusted.key_id, release_payload(package=PACKAGE))
    _, other = new_key("other")
    with pytest.raises(ManifestSignatureError):
        reader_for(other).read(raw)
    revoked = TrustedKey(trusted.key_id, trusted.public_key_b64, revoked=True)
    with pytest.raises(ManifestSignatureError):
        SignedManifestReader(TrustedKeyring([revoked])).read(raw)
    with pytest.raises(ManifestSignatureError, match="clave de firma"):
        SignedManifestReader(TrustedKeyring([])).read(raw)


def test_rotation_accepts_any_trusted_signature(key):
    private, trusted = key
    new_private, new_trusted = new_key("test-2026b")
    payload = release_payload(package=PACKAGE)
    first = ManifestSigner(private, trusted.key_id).sign(payload)
    both = ManifestSigner(new_private, new_trusted.key_id).sign(
        payload, existing_signatures=first["signatures"])
    raw = json.dumps(both).encode()
    assert reader_for(trusted).read(raw).key_id == trusted.key_id
    assert reader_for(new_trusted).read(raw).key_id == new_trusted.key_id


def test_forged_signature_bytes_are_rejected(key):
    private, trusted = key
    envelope = json.loads(signed_bytes(private, trusted.key_id, release_payload(package=PACKAGE)))
    envelope["signatures"][0]["signature"] = base64.b64encode(b"\x00" * 64).decode()
    with pytest.raises(ManifestSignatureError):
        reader_for(trusted).read(json.dumps(envelope).encode())


@pytest.mark.parametrize("raw", [b"not json", b"[]", json.dumps({"format": "x"}).encode(),
                                 b"{" + b" " * (300 * 1024) + b"}"],
                         ids=["not-json", "array", "wrong-format", "oversized"])
def test_malformed_envelopes_are_rejected(key, raw):
    with pytest.raises(ManifestFormatError):
        reader_for(key[1]).read(raw)


def test_signed_but_invalid_payload_is_still_rejected(key):
    private, trusted = key
    payload = release_payload(package=PACKAGE)
    payload["artifact"]["url"] = "http://" + HOST + "/x/" + payload["artifact"]["file_name"]
    # The signer refuses to sign it…
    with pytest.raises(ManifestValidationError):
        ManifestSigner(private, trusted.key_id).sign(payload)
    # …and a manifest signed by other means is still validated after verification.
    from backend.infrastructure.updater.update_manifest import canonical_payload_bytes
    signature = base64.b64encode(private.sign(canonical_payload_bytes(payload))).decode()
    raw = json.dumps({"format": "spj-signed-manifest/1", "payload": payload, "signatures": [
        {"key_id": trusted.key_id, "algorithm": "ed25519", "signature": signature}]}).encode()
    with pytest.raises(ManifestValidationError):
        reader_for(trusted).read(raw)


# ── downloads ──────────────────────────────────────────────────────────────
def _artifact(package=PACKAGE, **overrides):
    return ReleaseManifest.from_payload(release_payload(package=package, **overrides)).artifact


def _downloader(tmp_path, routes):
    opener = FakeOpener(routes)
    return UpdateDownloader(tmp_path / "downloads", allowed_hosts=frozenset({HOST}),
                            opener=opener), opener


def test_download_verifies_and_renames_atomically(tmp_path):
    artifact = _artifact()
    downloader, _ = _downloader(tmp_path, {artifact.url: (PACKAGE, None, len(PACKAGE))})
    progress = []
    path = downloader.download(artifact, progress=lambda done, total: progress.append(done))
    assert path.read_bytes() == PACKAGE
    assert not list((tmp_path / "downloads").glob("*.part"))
    assert progress[-1] == len(PACKAGE)


def test_hash_mismatch_leaves_nothing_behind(tmp_path):
    artifact = _artifact()
    tampered = PACKAGE[:-1] + b"X"
    downloader, _ = _downloader(tmp_path, {artifact.url: (tampered, None, None)})
    with pytest.raises(PackageDownloadError, match="SHA-256"):
        downloader.download(artifact)
    assert not any((tmp_path / "downloads").iterdir())


def test_oversized_responses_are_cut_off(tmp_path):
    artifact = _artifact()
    downloader, _ = _downloader(tmp_path, {artifact.url: (PACKAGE + b"extra", None, None)})
    with pytest.raises(PackageDownloadError, match="más de"):
        downloader.download(artifact)
    declared, _ = _downloader(tmp_path, {artifact.url: (PACKAGE, None, 10 ** 9)})
    with pytest.raises(PackageDownloadError, match="anuncia"):
        declared.download(artifact)
    assert not any((tmp_path / "downloads").iterdir())


def test_redirect_to_another_host_is_rejected(tmp_path):
    artifact = _artifact()
    downloader, _ = _downloader(
        tmp_path, {artifact.url: (PACKAGE, "https://evil.example/x.exe", None)})
    with pytest.raises(PackageDownloadError, match="no autorizado"):
        downloader.download(artifact)


def test_disallowed_host_is_never_contacted(tmp_path):
    artifact = _artifact(host="evil.example")
    downloader, opener = _downloader(tmp_path, {})
    with pytest.raises(PackageDownloadError, match="no autorizado"):
        downloader.download(artifact)
    assert opener.requests == []
    with pytest.raises(PackageDownloadError, match="HTTPS"):
        downloader.fetch_manifest(f"http://{HOST}/stable/manifest.json")


def test_cancel_removes_partial_file(tmp_path):
    artifact = _artifact()
    downloader, _ = _downloader(tmp_path, {artifact.url: (PACKAGE, None, None)})
    with pytest.raises(DownloadCancelledError):
        downloader.download(artifact, cancelled=lambda: True)
    assert not any((tmp_path / "downloads").iterdir())


def test_verified_file_is_reused_and_tampered_file_is_replaced(tmp_path):
    artifact = _artifact()
    downloader, opener = _downloader(tmp_path, {artifact.url: (PACKAGE, None, None)})
    path = downloader.download(artifact)
    downloader.download(artifact)
    assert len(opener.requests) == 1  # reused
    path.write_bytes(b"tampered")
    assert downloader.download(artifact).read_bytes() == PACKAGE
    assert len(opener.requests) == 2
