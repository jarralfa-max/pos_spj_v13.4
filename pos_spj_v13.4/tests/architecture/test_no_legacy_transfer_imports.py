from pathlib import Path


ROOT = Path("pos_spj_v13.4")


def test_no_legacy_transfer_modules_imports_routes_or_events():
    assert not (ROOT / "modulos/transferencias.py").exists()
    assert not (ROOT / "repositories/transferencias.py").exists()
    files = []
    for folder in ("backend", "core", "frontend", "interfaz"):
        files.extend((ROOT / folder).rglob("*.py"))
    sources = "\n".join(path.read_text(errors="ignore") for path in files)
    for legacy in ("modulos.transferencias", "repositories.transferencias",
                   "TRASPASO_INICIADO", "TRASPASO_CONFIRMADO",
                   "TRASPASO_CANCELADO", "TRANSFER_ITEMS_PROCESS"):
        assert legacy not in sources


def test_only_canonical_transfer_schema_is_created():
    sources = "\n".join(path.read_text(errors="ignore") for path in (
        list((ROOT / "migrations").rglob("*.py"))
        + list((ROOT / "backend/infrastructure/db/schema").rglob("*.py"))))
    for legacy_table in ("CREATE TABLE IF NOT EXISTS transferencias ",
                         "CREATE TABLE IF NOT EXISTS transferencia_detalle ",
                         "CREATE TABLE IF NOT EXISTS transfers ",
                         "CREATE TABLE IF NOT EXISTS transfer_items ",
                         "CREATE TABLE IF NOT EXISTS inventory_transfer "):
        assert legacy_table not in sources
    assert "CREATE TABLE IF NOT EXISTS stock_transfers" in sources
