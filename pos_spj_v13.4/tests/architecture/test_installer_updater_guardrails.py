"""Guardrails of the installer/updater (2026-10-14).

Each test pins a rule the external audit found broken or that would silently
regress: one version source, one database path resolver, no shell or
unverified download in the updater, no Qt in the external updater, the
install-profile catalog in sync with the real shell modules, and the
seeded permissions matching the codes the use cases require.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UPDATER_FILES = [
    *sorted((ROOT / "backend" / "infrastructure" / "updater").glob("*.py")),
    ROOT / "backend" / "infrastructure" / "db" / "sqlite_backup.py",
    ROOT / "backend" / "infrastructure" / "db" / "database_relocation.py",
    *sorted((ROOT / "backend" / "application" / "software_updates").glob("*.py")),
]
CODE_ROOTS = ("backend", "frontend", "migrations")


def _calls(tree: ast.AST) -> list[str]:
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
                names.append(f"{func.value.id}.{func.attr}")
            elif isinstance(func, ast.Name):
                names.append(func.id)
    return names


def test_updater_never_uses_a_shell_or_unverified_download():
    offenders = []
    for path in UPDATER_FILES:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = _calls(tree)
        for forbidden in ("os.system", "os.popen", "urlretrieve", "eval", "exec"):
            if forbidden in calls:
                offenders.append(f"{path.name}: {forbidden}")
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "shell":
                if not (isinstance(node.value, ast.Constant) and node.value.value is False):
                    offenders.append(f"{path.name}: shell=")
    assert not offenders, offenders


def test_sqlite_files_are_never_byte_copied():
    """A live WAL database copied byte by byte can be torn; backups and the
    relocation go through the SQLite backup API."""
    for name in ("sqlite_backup.py",):
        source = (ROOT / "backend" / "infrastructure" / "db" / name).read_text(encoding="utf-8")
        calls = _calls(ast.parse(source))
        assert not [c for c in calls if c.startswith("shutil.copy")], name
    relocation = (ROOT / "backend" / "infrastructure" / "db" / "database_relocation.py")
    tree = ast.parse(relocation.read_text(encoding="utf-8"))
    copy_calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Attribute) and n.func.attr.startswith("copy")
                  and isinstance(n.func.value, ast.Name) and n.func.value.id == "shutil"]
    # Only the media companion copy, inside _copy_companions.
    assert len(copy_calls) == 1


def test_single_version_source():
    assert not (ROOT / "version.py").exists(), "version.py se retiró: la fuente es app_version.py"
    pattern = re.compile(r"^\s*(__version__|VERSION)\s*=\s*['\"]\d+\.\d+", re.M)
    offenders = []
    for top in CODE_ROOTS:
        for path in (ROOT / top).rglob("*.py"):
            if path.name == "app_version.py" or "tests" in path.parts:
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(path.relative_to(ROOT)))
    assert not offenders, offenders


def test_database_file_name_is_resolved_in_one_place():
    """Only `AppPaths` names the database file; everyone else asks it."""
    offenders = []
    for top in CODE_ROOTS:
        for path in (ROOT / top).rglob("*.py"):
            if "tests" in path.parts or path.name == "app_paths.py":
                continue
            tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
            docstrings = {
                id(node.body[0].value) for node in ast.walk(tree)
                if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                                     ast.AsyncFunctionDef))
                and node.body and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
            }
            for node in ast.walk(tree):
                if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                        and "spj_pos_database.db" in node.value and id(node) not in docstrings):
                    offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, offenders


def test_external_updater_does_not_load_qt_or_the_erp():
    script = (
        "import sys; sys.path.insert(0, %r); "
        "import backend.infrastructure.updater.updater_main; "
        "bad = [m for m in sys.modules if m.startswith(('PyQt5', 'frontend', 'cryptography'))]; "
        "print(','.join(bad))" % str(ROOT))
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                               timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "", completed.stdout


def test_install_profile_catalog_matches_the_shell_modules():
    from backend.domain.software_distribution.install_profile import ALL_CAPABILITIES

    module_ids = set()
    for registration in (ROOT / "frontend" / "desktop" / "modules").glob("*/shell_registration.py"):
        match = re.search(r'^[A-Z_]+_MODULE_ID\s*=\s*"([a-z_]+)"',
                          registration.read_text(encoding="utf-8"), re.M)
        if match:
            module_ids.add(match.group(1))
    assert module_ids == set(ALL_CAPABILITIES), (
        f"sin perfil: {sorted(module_ids - ALL_CAPABILITIES)}; "
        f"sobran: {sorted(ALL_CAPABILITIES - module_ids)}")


def test_seeded_update_permissions_are_the_ones_the_use_cases_require():
    import importlib

    from backend.application.configuracion.permissions import ConfiguracionPermissions as P

    seed = importlib.import_module("migrations.standalone.339_seed_software_update_permissions")
    seeded = {f"CONFIGURACION.{action}" for action in seed._ADMIN_ACTIONS}
    assert seeded == {P.ACTUALIZACIONES_VIEW, P.ACTUALIZACIONES_ADMINISTRAR,
                      P.ACTUALIZACIONES_CANAL}
    assert seed._PLAN["solo_lectura"] == ("actualizacion.ver",)


def test_trusted_keys_are_embedded_constants_not_read_from_files():
    source = (ROOT / "backend" / "infrastructure" / "updater" / "trusted_keys.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    assert not [c for c in _calls(tree) if c in ("open", "Path.read_text", "json.load")]
    assert "os.environ" not in source
