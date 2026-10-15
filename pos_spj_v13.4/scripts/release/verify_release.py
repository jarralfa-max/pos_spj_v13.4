"""Verify a release folder the way a station would — and decide if it may be
published.

    python scripts/release/verify_release.py build/windows/release [--production]
        [--public-key <base64> --key-id <id>]   (development key instead of the embedded ones)

Checks: the manifest is signed by a trusted key (the keys EMBEDDED in this
code base unless a development key is given), the payload is valid, the
installer's size and SHA-256 match, and its Authenticode signature status.
`--production` fails unless the installer is Authenticode-signed AND the
manifest verifies with an embedded production key. Exit code 0 = OK.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from _release_common import sha256_file

from backend.infrastructure.updater.installer_trust import AuthenticodeVerifier
from backend.infrastructure.updater.trusted_keys import embedded_keyring
from backend.infrastructure.updater.update_manifest import (
    SignedManifestReader,
    TrustedKey,
    TrustedKeyring,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--public-key", default="")
    parser.add_argument("--key-id", default="dev")
    args = parser.parse_args(argv)
    folder = args.release_dir
    problems: list[str] = []

    keyring = (TrustedKeyring([TrustedKey(args.key_id, args.public_key)]) if args.public_key
               else embedded_keyring())
    manifest_path = folder / "manifest.json"
    manifest = None
    if not manifest_path.exists():
        problems.append("Falta manifest.json (firme manifest.payload.json).")
    else:
        try:
            authenticated = SignedManifestReader(keyring).read(manifest_path.read_bytes())
            manifest = authenticated.manifest
            print(f"Manifiesto: versión {manifest.version}, canal {manifest.channel.value}, "
                  f"firmado por {authenticated.key_id}")
        except Exception as exc:
            problems.append(f"Manifiesto inválido: {exc}")

    if manifest is not None:
        installer = folder / manifest.artifact.file_name
        if not installer.exists():
            problems.append(f"Falta el instalador {installer.name}.")
        else:
            if installer.stat().st_size != manifest.artifact.size:
                problems.append("El tamaño del instalador no coincide con el manifiesto.")
            if sha256_file(installer) != manifest.artifact.sha256:
                problems.append("El SHA-256 del instalador no coincide con el manifiesto.")
            signature = AuthenticodeVerifier.inspect(installer)
            print(f"Authenticode: {signature.status} {signature.subject}")
            if args.production and not signature.valid:
                problems.append("El instalador no tiene firma Authenticode válida.")
    if args.production and args.public_key:
        problems.append("Producción exige una clave embebida, no una clave de desarrollo.")

    release_json = folder / "release.json"
    if release_json.exists():
        release = json.loads(release_json.read_text(encoding="utf-8"))
        print(f"release.json: publishable={release.get('publishable')} {release.get('reason', '')}")
    for problem in problems:
        print("ERROR:", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
