"""Build the Windows release: PyInstaller bundle + updater + Inno Setup installer.

Run on WINDOWS with the pinned build environment:

    py -3.13 -m venv .buildvenv
    .buildvenv\\Scripts\\python -m pip install -r pos_spj_v13.4\\installer\\windows\\requirements-release.txt
    .buildvenv\\Scripts\\python pos_spj_v13.4\\scripts\\release\\build_windows_release.py ^
        --channel stable --build-number 42 ^
        --artifact-base-url https://updates.example.com/spj/stable ^
        --feed-url "https://updates.example.com/spj/{channel}/manifest.json"

Output (default `<repo>/build/windows/release/`):

    SPJ-Setup-<version>-x64.exe          the installer
    SPJ-Setup-<version>-x64.exe.sha256   its hash
    manifest.payload.json                UNSIGNED manifest payload (sign with
                                         sign_manifest.py → manifest.json)
    release.json                         version, commit, hashes, signed flags,
                                         and `publishable` (false until BOTH the
                                         installer has a valid Authenticode
                                         signature and the manifest is signed)

Signing (Authenticode) happens only when `--sign` is given and the signing
command is configured in `SPJ_SIGNTOOL` (e.g. `signtool sign /fd sha256 /tr
http://timestamp.digicert.com /td sha256 /sha1 <THUMBPRINT>`): this script
never invents a certificate. Without it the build is a development build,
marked `"publishable": false`.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
import shutil
import sys

from _release_common import (
    DEFAULT_BUILD_DIR,
    PACKAGE_ROOT,
    git_commit,
    read_version,
    run,
    schema_target,
    sha256_file,
    write_json,
)

INSTALLER_DIR = PACKAGE_ROOT / "installer" / "windows"
#: `C:\Program Files\SPJ\SPJ ERP POS\` (33) + this must stay below MAX_PATH (260),
#: with room for a longer custom installation folder.
INSTALL_DIR_EXAMPLE = r"C:\Program Files\SPJ\SPJ ERP POS"
MAX_BUNDLE_RELATIVE_PATH = 180
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)


def parse_arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--channel", choices=("stable", "pilot"), default="stable")
    parser.add_argument("--build-number", default=os.environ.get("GITHUB_RUN_NUMBER", "0"))
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--artifact-base-url", default="",
                        help="HTTPS URL of the folder that will host the installer")
    parser.add_argument("--feed-url", default="",
                        help="Manifest URL template written into install_config.json")
    parser.add_argument("--allowed-hosts", default="",
                        help="Comma-separated hosts the station may download from")
    parser.add_argument("--minimum-installed-version", default="")
    parser.add_argument("--schema-requires-at-least", type=int, default=0)
    parser.add_argument("--release-notes", default="")
    parser.add_argument("--iscc", default="")
    parser.add_argument("--sign", action="store_true")
    parser.add_argument("--skip-installer", action="store_true")
    return parser.parse_args(argv)


def version_info_text(version: str, file_version: str, build_number: str) -> str:
    parts = tuple(int(p) for p in file_version.split("."))
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(filevers={parts}, prodvers={parts}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('080a04b0', [
      StringStruct('CompanyName', 'SPJ'),
      StringStruct('FileDescription', 'SPJ ERP POS'),
      StringStruct('FileVersion', '{file_version}'),
      StringStruct('InternalName', 'SPJ'),
      StringStruct('ProductName', 'SPJ ERP POS'),
      StringStruct('ProductVersion', '{version} (build {build_number})')])]),
    VarFileInfo([VarStruct('Translation', [2058, 1200])])
  ]
)
"""


def render_icon(build_dir: Path) -> Path | None:
    """`spj.ico` from the OFFICIAL `assets/branding/app_icon.svg` — a format
    conversion for Windows, never a new design. Skipped (no icon) if Qt's SVG
    renderer is unavailable."""
    source = PACKAGE_ROOT / "assets" / "branding" / "app_icon.svg"
    if not source.exists():
        return None
    try:
        from PIL import Image
        from PyQt5.QtCore import QByteArray, Qt
        from PyQt5.QtGui import QGuiApplication, QImage, QPainter
        from PyQt5.QtSvg import QSvgRenderer
    except ImportError:
        print("Aviso: sin PyQt5.QtSvg/Pillow; el .exe no llevará icono.")
        return None
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QGuiApplication.instance() or QGuiApplication([])
    svg = source.read_text(encoding="utf-8").replace(' href="', ' xlink:href="')
    if "xmlns:xlink" not in svg:
        svg = svg.replace("<svg ", '<svg xmlns:xlink="http://www.w3.org/1999/xlink" ', 1)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    images = []
    for size in ICON_SIZES:
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        png = build_dir / f"icon-{size}.png"
        image.save(str(png))
        images.append(Image.open(png).convert("RGBA"))
    target = build_dir / "spj.ico"
    images[-1].save(target, sizes=[(s, s) for s in ICON_SIZES], append_images=images[:-1])
    del app
    return target


def signtool_command() -> list[str]:
    configured = os.environ.get("SPJ_SIGNTOOL", "")
    if not configured:
        raise SystemExit("--sign requiere SPJ_SIGNTOOL con el comando de firma configurado.")
    return shlex.split(configured, posix=False)


def sign(paths: list[Path]) -> None:
    command = signtool_command()
    for path in paths:
        run([*command, str(path)])


def find_iscc(explicit: str) -> Path:
    candidates = [explicit] if explicit else []
    candidates += [shutil.which("iscc") or "",
                   r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
                   r"C:\Program Files\Inno Setup 6\ISCC.exe"]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate)
    raise SystemExit("No se encontró ISCC.exe (Inno Setup 6). Use --iscc o instálelo.")


def main(argv=None) -> int:
    args = parse_arguments(argv)
    if sys.platform != "win32":
        raise SystemExit("El release de Windows se construye en Windows (runner windows-latest).")
    from backend.domain.software_distribution.semantic_version import SemanticVersion

    version = read_version()
    semver = SemanticVersion.parse(version)
    file_version = semver.windows_file_version()
    # absolute(), not resolve(): resolve() expands an 8.3 short path back to the
    # long one, and Inno Setup cannot read files past MAX_PATH (260).
    build_dir = args.build_dir.absolute()
    release_dir = build_dir / "release"
    dist_dir = build_dir / "dist"
    for folder in (release_dir, dist_dir, build_dir / "work"):
        shutil.rmtree(folder, ignore_errors=True)
    release_dir.mkdir(parents=True)

    commit = git_commit()
    build_info = {
        "version": version, "commit": commit, "build_number": str(args.build_number),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channel": args.channel, "signed": bool(args.sign),
        "python": sys.version.split()[0],
    }
    write_json(build_dir / "build_info.json", build_info)
    (build_dir / "version_info.txt").write_text(
        version_info_text(version, file_version, str(args.build_number)), encoding="utf-8")
    render_icon(build_dir)

    environment = dict(os.environ, SPJ_BUILD_DIR=str(build_dir))
    for spec in ("spj.spec", "spj_updater.spec"):
        run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
             "--distpath", str(dist_dir), "--workpath", str(build_dir / "work"),
             str(INSTALLER_DIR / spec)], env=environment)

    bundle = dist_dir / "SPJ"
    updater = dist_dir / "spj_updater.exe"
    longest = max(len(str(path.relative_to(bundle))) for path in bundle.rglob("*"))
    if longest > MAX_BUNDLE_RELATIVE_PATH:
        raise SystemExit(
            f"Una ruta del paquete mide {longest} caracteres; instalada en "
            f"'{INSTALL_DIR_EXAMPLE}' superaría el límite de Windows (260).")
    if args.sign:
        sign([bundle / "SPJ.exe", bundle / "spj_whatsapp.exe", updater])

    result = {**build_info, "schema_target": schema_target(), "bundle": str(bundle),
              "longest_bundle_path": longest}
    if args.skip_installer:
        write_json(release_dir / "release.json", {**result, "publishable": False,
                                                  "reason": "sin instalador (--skip-installer)"})
        return 0

    hosts = args.allowed_hosts
    if not hosts and args.feed_url:
        from urllib.parse import urlsplit
        hosts = urlsplit(args.feed_url.replace("{channel}", args.channel)).hostname or ""
    iscc = find_iscc(args.iscc)
    command = [
        str(iscc), f"/DAppVersion={version}", f"/DFileVersion={file_version}",
        f"/DSourceDir={bundle}", f"/DUpdaterExe={updater}", f"/DBuildDir={build_dir}",
        f"/DOutputDir={release_dir}", f"/DFeedUrl={args.feed_url}",
        f"/DAllowedHosts={hosts}", f"/DDefaultChannel={args.channel}",
    ]
    if args.sign:
        command += ["/DSIGN", "/Sspjsign=" + " ".join(signtool_command()) + " $f"]
    command.append(str(INSTALLER_DIR / "spj_setup.iss"))
    run(command)

    installer = release_dir / f"SPJ-Setup-{version}-x64.exe"
    digest = sha256_file(installer)
    (release_dir / f"{installer.name}.sha256").write_text(f"{digest}  {installer.name}\n",
                                                          encoding="ascii")
    if args.artifact_base_url:
        from backend.domain.software_distribution.release_manifest import ReleaseManifest

        payload = {
            "format": "spj-release/1", "product": "spj-erp-pos", "version": version,
            "channel": args.channel, "published_at": build_info["built_at"].replace("+00:00", "Z"),
            "platform": {"os": "windows", "arch": "x64"},
            "minimum_installed_version": args.minimum_installed_version or None,
            "database_schema": {"requires_at_least": args.schema_requires_at_least,
                                "migrates_to": schema_target()},
            "artifact": {"kind": "inno-setup", "file_name": installer.name,
                         "url": f"{args.artifact_base_url.rstrip('/')}/{installer.name}",
                         "size": installer.stat().st_size, "sha256": digest},
            "release_notes": args.release_notes, "mandatory": False,
            "mandatory_deadline": None,
            "rollout": {"percent": 100, "branch_ids": [], "workstation_ids": []},
        }
        ReleaseManifest.from_payload(payload)  # never emit what clients would reject
        write_json(release_dir / "manifest.payload.json", payload)
    write_json(release_dir / "release.json", {
        **result, "installer": installer.name, "installer_sha256": digest,
        "installer_size": installer.stat().st_size,
        "authenticode_signed": bool(args.sign), "manifest_signed": False,
        "publishable": False,
        "reason": ("falta firmar el manifiesto (sign_manifest.py)" if args.sign
                   else "compilación de desarrollo: sin firma Authenticode"),
    })
    print(f"Instalador: {installer}\nSHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
