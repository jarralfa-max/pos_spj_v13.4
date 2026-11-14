"""SDLC-INST-003 — permisos mínimos de la carpeta de datos de alcance máquina.

Las PCs de sucursal tienen varios usuarios de Windows y la aplicación corre como
cada uno, así que todos necesitan escribir en las carpetas donde trabaja. Lo que
ya no necesitan es Modificar sobre la raíz: desde ahí se podía renombrar o
reemplazar cualquiera de ellas.

El instalador no se ejecuta aquí. La prueba de Windows aplica los mismos comandos
de `icacls` a un árbol temporal que imita el permiso de una instalación anterior.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

import pytest

from backend.shared.app_paths import LAYOUT_INSTALLED, AppPaths
from backend.shared.install_config import InstallConfig

ROOT = Path(__file__).resolve().parents[3]
ISS = (ROOT / "installer" / "windows" / "spj_setup.iss").read_text(encoding="utf-8")
USERS_SID = "*S-1-5-32-545"
DATA_ROOT = r"{commonappdata}\SPJ\{#AppName}"


def _writable_folders() -> list[str]:
    block = ISS[ISS.index("function WritableDataFolders"):]
    block = block[:block.index("end;")]
    return re.findall(r"'([a-z_]+)'", block)


def _first_level(paths: AppPaths, path: Path) -> str:
    return path.relative_to(paths.user_data_dir).parts[0]


def test_every_folder_the_application_writes_is_listed(tmp_path):
    paths = AppPaths(base_dir=tmp_path / "app", data_dir=tmp_path / "data",
                     layout=LAYOUT_INSTALLED, install_config=InstallConfig(data_scope="machine"))
    expected = {_first_level(paths, path) for path in (
        paths.database_dir, paths.backups_dir, paths.logs_dir, paths.product_images_dir,
        paths.branding_dir, paths.display_media_dir, paths.whatsapp_data_dir, paths.updater_dir,
        paths.downloads_dir, paths.manifests_dir)}
    assert expected <= set(_writable_folders())


def test_no_code_writes_under_an_unlisted_folder():
    """Una carpeta nueva bajo la raíz debe agregarse al instalador: sin ella, un
    usuario normal no podría trabajar ahí."""
    pattern = re.compile(r'(?:user_data_dir|data_root)\s*/\s*"([^"]+)"')
    found: dict[str, str] = {}
    for path in (ROOT / "backend").rglob("*.py"):
        for name in pattern.findall(path.read_text(encoding="utf-8", errors="ignore")):
            found[name] = str(path.relative_to(ROOT))
    unlisted = {name: where for name, where in found.items()
                if name not in _writable_folders()}
    assert not unlisted, unlisted


def test_root_no_longer_grants_modify_to_every_user():
    assert not re.search(r'Name: "\{commonappdata\}\\SPJ\\\{#AppName\}";.*users-modify', ISS)
    assert 'Name: "' + DATA_ROOT + '"' in ISS


def test_installer_narrows_the_root_after_granting_the_folders():
    procedure = ISS[ISS.index("procedure ApplyDataFolderPermissions"):]
    procedure = procedure[:procedure.index("end;\n\nprocedure") if "end;\n\nprocedure" in procedure
                          else len(procedure)]
    grant = procedure.index("(OI)(CI)M")
    narrow = procedure.index("/grant:r")
    assert grant < narrow
    assert "(OI)(CI)(RX)" in procedure
    # Si una carpeta no quedó con permiso, la raíz no se toca: nadie pierde escritura.
    assert "Exit;" in procedure[grant:narrow]
    assert "IsMachineScope" in procedure
    assert "ApplyDataFolderPermissions;" in ISS[ISS.index("procedure CurStepChanged"):]


def test_ci_checks_the_permissions():
    workflow = (ROOT.parent / ".github" / "workflows" / "windows-release.yml").read_text(
        encoding="utf-8")
    assert "La raiz de datos sigue con Modificar" in workflow


def _rights(path: Path, tmp_path: Path) -> str:
    saved = tmp_path / "acl.txt"
    subprocess.run(["icacls", str(path), "/save", str(saved)], check=True, capture_output=True)
    return saved.read_bytes().decode("utf-16-le", errors="ignore")


def _users_can_write(sddl: str) -> bool:
    """¿Alguna entrada de Users da Modificar? 0x1301bf es la máscara de `M`."""
    for rights in re.findall(r"\(A;[^;]*;([^;]*);;;BU\)", sddl):
        if rights in {"0x1301bf", "FA"} or "SD" in rights:
            return True
    return False


@pytest.mark.skipif(sys.platform != "win32", reason="icacls sólo existe en Windows")
def test_commands_leave_folders_writable_and_root_narrowed(tmp_path):
    root = tmp_path / "datos"
    db = root / "db"
    db.mkdir(parents=True)
    (db / "spj.db").write_bytes(b"x")
    (root / "suelto.txt").write_bytes(b"x")
    # Lo que dejó el instalador anterior: Modificar en la raíz.
    subprocess.run(["icacls", str(root), "/grant", f"{USERS_SID}:(OI)(CI)M"],
                   check=True, capture_output=True)
    assert _users_can_write(_rights(root / "suelto.txt", tmp_path))

    subprocess.run(["icacls", str(db), "/grant", f"{USERS_SID}:(OI)(CI)M"],
                   check=True, capture_output=True)
    subprocess.run(["icacls", str(root), "/grant:r", f"{USERS_SID}:(OI)(CI)(RX)"],
                   check=True, capture_output=True)

    assert _users_can_write(_rights(db / "spj.db", tmp_path))
    assert not _users_can_write(_rights(root / "suelto.txt", tmp_path))
