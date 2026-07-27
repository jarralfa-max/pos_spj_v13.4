"""
test_migration_audit.py — v13.4
Verifica que el script de auditoría de migraciones funciona correctamente.
"""
import sys
import os

# Agrega tanto el directorio del paquete como el root del repo al path
_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PKG_DIR = os.path.dirname(_TESTS_DIR)          # pos_spj_v13.4/
_ROOT_DIR = os.path.dirname(_PKG_DIR)           # repo root
for _p in [_PKG_DIR, _ROOT_DIR]:
    if _p not in sys.path:
        sys.path.insert(0, _p)


def _load_audit_script():
    import importlib.util
    script_path = os.path.join(_ROOT_DIR, "scripts", "audit_migrations.py")
    spec = importlib.util.spec_from_file_location("audit_migrations", script_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_scan_standalone_finds_files():
    mod = _load_audit_script()
    nums = mod.scan_standalone()
    assert len(nums) > 0
    # Los canónicos deben estar presentes
    assert "030" in nums
    assert "031" in nums
    assert "032" in nums
    assert "048" in nums


def test_scan_engine_finds_registered():
    mod = _load_audit_script()
    registered = mod.scan_engine()
    assert "030" in registered
    assert "051" in registered
    # Nuevas migraciones v13.4
    assert "052" in registered
    assert "053" in registered
    assert "054" in registered


def test_orphans_030_031_are_comment_only():
    """030_recipe_tables y 031_inventory_industrial son solo comentarios."""
    from pathlib import Path
    base = Path(__file__).parent.parent / "migrations" / "standalone"

    for fname in ["030_recipe_tables.py", "031_inventory_industrial.py"]:
        path = base / fname
        assert path.exists(), f"{fname} no existe"
        content = path.read_text().strip()
        # No debe tener código ejecutable real (solo comentarios)
        has_run = "def run(" in content or "def up(" in content or "def crear_tablas(" in content
        assert not has_run, f"{fname} tiene función de migración activa pero debería ser solo comentario"


def test_new_migrations_053_054_have_run():
    """053 y 054 deben tener función run()."""
    from pathlib import Path
    base = Path(__file__).parent.parent / "migrations" / "standalone"

    for fname in ["053_meat_production_tables.py", "054_sync_improvements_orphan.py"]:
        path = base / fname
        assert path.exists(), f"{fname} no existe"
        content = path.read_text()
        assert "def run(" in content, f"{fname} no tiene función run()"
