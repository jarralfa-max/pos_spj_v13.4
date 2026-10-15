"""Generate an Ed25519 release-manifest signing key.

    python scripts/release/generate_signing_key.py --key-id spj-release-2026a \
        --out D:\\llaves\\spj-release-2026a.pem

Writes the PRIVATE key (PEM, optionally encrypted with --passphrase-env) to
`--out`, which must be OUTSIDE the repository, and prints the `TrustedKey`
line to paste into `backend/infrastructure/updater/trusted_keys.py`. Store the
private key as the CI secret `SPJ_MANIFEST_SIGNING_KEY` (base64 of the PEM) or
on an offline signing machine. Never commit it.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

from _release_common import REPO_ROOT

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from backend.infrastructure.updater.update_manifest import ManifestSigner


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--passphrase-env", default="",
                        help="Environment variable holding a passphrase to encrypt the PEM")
    args = parser.parse_args(argv)
    out = args.out.resolve()
    try:
        out.relative_to(REPO_ROOT.resolve())
        raise SystemExit("La clave privada no puede guardarse dentro del repositorio.")
    except ValueError:
        pass
    if out.exists():
        raise SystemExit(f"{out} ya existe; no se sobrescribe una clave.")
    key = Ed25519PrivateKey.generate()
    passphrase = os.environ.get(args.passphrase_env, "") if args.passphrase_env else ""
    encryption = (serialization.BestAvailableEncryption(passphrase.encode("utf-8"))
                  if passphrase else serialization.NoEncryption())
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            encryption)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pem)
    public = ManifestSigner.public_key_b64(key)
    print("Clave privada:", out)
    print("Pegue en backend/infrastructure/updater/trusted_keys.py → EMBEDDED_RELEASE_KEYS:")
    print(f'    TrustedKey("{args.key_id}", "{public}", note="…"),')
    return 0


if __name__ == "__main__":
    sys.exit(main())
