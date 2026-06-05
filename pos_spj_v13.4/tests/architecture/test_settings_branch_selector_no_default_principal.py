from pathlib import Path

CONFIGURATION_MODULE = Path("pos_spj_v13.4/modulos/configuracion.py")


def _method_block(content: str, method_name: str, next_method_name: str) -> str:
    start = content.index(f"    def {method_name}")
    end = content.index(f"    def {next_method_name}", start)
    return content[start:end]


def test_company_branch_selector_starts_with_explicit_placeholder() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    load_block = _method_block(content, "_cargar_empresa", "_guardar_empresa")

    assert '"-- Selecciona sucursal --", None' in load_block
    assert "branches_for_company_settings()" in load_block
    assert "No hay sucursales activas configuradas." in load_block
    assert "setCurrentIndex(index)" in load_block
    assert "Principal" not in load_block


def test_company_branch_selector_must_be_selected_before_save() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    save_block = _method_block(content, "_guardar_empresa", "_seleccionar_logo")

    assert "if suc_id is None:" in save_block
    assert "Selecciona la sucursal de esta terminal." in save_block
    assert "'sucursal_instalacion_id': str(suc_id)" in save_block
    assert "currentData() or 1" not in save_block
    assert "sucursal_instalacion_id'] = str(1)" not in save_block
    assert "Principal" not in save_block
