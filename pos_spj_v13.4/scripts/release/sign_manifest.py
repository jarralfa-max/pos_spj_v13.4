"""Sign a release manifest payload (Ed25519) → `manifest.json`.

    python scripts/release/sign_manifest.py --payload build/windows/release/manifest.payload.json \
        --key-id spj-release-2026a --key-file D:\\llaves\\spj-release-2026a.pem \
        --out build/windows/release/manifest.json

The key can come from `--key-file` or from the environment variable named by
`--key-env` (base64 of the PEM; the CI secret `SPJ_MANIFEST_SIGNING_KEY`).
`--existing` keeps the signatures of an already signed manifest (key rotation:
sign with the old and the new key). The payload is validated BEFORE signing:
nothing a station would reject gets signed.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import sys

from _release_common import write_json

from cryptography.hazmat.primitives import serialization

from backend.infrastructure.updater.update_manifest import ManifestSigner


def load_private_key(args):
    if args.key_file:
        pem = Path(args.key_file).read_bytes()
    elif args.key_env and os.environ.get(args.key_env):
        pem = base64.b64decode(os.environ[args.key_env])
    else:
        raise SystemExit("Indique --key-file o --key-env con la clave privada.")
    passphrase = os.environ.get(args.passphrase_env, "") if args.passphrase_env else ""
    return serialization.load_pem_private_key(pem, password=passphrase.encode() or None)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload", required=True, type=Path)
    parser.add_argument("--key-id", required=True)
    parser.add_argument("--key-file", default="")
    parser.add_argument("--key-env", default="SPJ_MANIFEST_SIGNING_KEY")
    parser.add_argument("--passphrase-env", default="")
    parser.add_argument("--existing", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.payload.read_text(encoding="utf-8"))
    existing = []
    if args.existing:
        envelope = json.loads(args.existing.read_text(encoding="utf-8"))
        if envelope.get("payload") != payload:
            raise SystemExit("--existing firma otro contenido; no se mezclan firmas.")
        existing = envelope.get("signatures", [])
    signed = ManifestSigner(load_private_key(args), args.key_id).sign(
        payload, existing_signatures=existing)
    write_json(args.out, signed)
    release_json = args.out.parent / "release.json"
    if release_json.exists():
        release = json.loads(release_json.read_text(encoding="utf-8"))
        release["manifest_signed"] = True
        release["manifest_key_ids"] = [s["key_id"] for s in signed["signatures"]]
        release["publishable"] = bool(release.get("authenticode_signed"))
        release["reason"] = ("" if release["publishable"]
                             else "compilación de desarrollo: sin firma Authenticode")
        write_json(release_json, release)
    print(f"Manifiesto firmado: {args.out} (claves: "
          f"{', '.join(s['key_id'] for s in signed['signatures'])})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
