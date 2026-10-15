"""Assemble the OFFLINE update package for removable media.

    python scripts/release/make_offline_package.py build/windows/release E:\\SPJ-13.5.0

Copies the signed `manifest.json` and the installer it names into the target
folder (verifying size and SHA-256 after the copy) and adds LEEME.txt. At the
branch: Configuración → Acerca de y actualizaciones → «Importar paquete
offline…» → choose `manifest.json`. The station applies exactly the same
signature, hash, channel, platform, version and schema checks as online.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
import sys

from _release_common import sha256_file

from backend.infrastructure.updater.trusted_keys import embedded_keyring
from backend.infrastructure.updater.update_manifest import (
    SignedManifestReader,
    TrustedKey,
    TrustedKeyring,
)

README = """Paquete offline de SPJ ERP POS {version} (canal {channel})

1. Conecte esta memoria en la estación.
2. SPJ → Configuración → Acerca de y actualizaciones → «Importar paquete offline…».
3. Elija manifest.json de esta carpeta. SPJ verifica la firma, el hash y que la
   versión corresponda a la estación antes de copiar nada.
4. Pulse «Instalar ahora» (sin ventas ni cortes en curso) o programe la ventana.

SHA-256 del instalador: {sha256}
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_dir", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--public-key", default="")
    parser.add_argument("--key-id", default="dev")
    args = parser.parse_args(argv)
    keyring = (TrustedKeyring([TrustedKey(args.key_id, args.public_key)]) if args.public_key
               else embedded_keyring())
    raw = (args.release_dir / "manifest.json").read_bytes()
    manifest = SignedManifestReader(keyring).read(raw).manifest
    installer = args.release_dir / manifest.artifact.file_name
    args.target.mkdir(parents=True, exist_ok=True)
    (args.target / "manifest.json").write_bytes(raw)
    copied = args.target / installer.name
    shutil.copyfile(installer, copied)
    if copied.stat().st_size != manifest.artifact.size or sha256_file(copied) != manifest.artifact.sha256:
        copied.unlink()
        raise SystemExit("La copia del instalador no coincide con el manifiesto; se borró.")
    (args.target / "LEEME.txt").write_text(README.format(
        version=manifest.version, channel=manifest.channel.label,
        sha256=manifest.artifact.sha256), encoding="utf-8")
    print(f"Paquete offline listo en {args.target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
