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
    # El combo filtra identidades corruptas (id NULL/""/None/null) y avisa
    # cuando no queda ninguna sucursal con UUID válido.
    assert '"", "none", "null"' in load_block
    assert "No hay sucursales válidas con UUID" in load_block
    assert "setCurrentIndex(index)" in load_block
    assert "Principal" not in load_block


def test_company_branch_selector_must_be_selected_before_save() -> None:
    content = CONFIGURATION_MODULE.read_text(encoding="utf-8")
    save_block = _method_block(content, "_guardar_empresa", "_seleccionar_logo")

    # Rechazo explícito de None/""/null ANTES de tocar la configuración:
    # jamás debe persistirse el string "None" como sucursal de la terminal.
    assert 'suc_id_str.lower() in ("", "none", "null")' in save_block
    assert "Sucursal inválida" in save_block
    # La clave se fija por la ruta canónica validada, no por save_many directo.
    assert "set_installation_branch(suc_id_str)" in save_block
    assert "'sucursal_instalacion_id': str(suc_id)" not in save_block
    assert "str(None)" not in save_block
    assert "currentData() or 1" not in save_block
    assert "sucursal_instalacion_id'] = str(1)" not in save_block
    assert "Principal" not in save_block
    # Tras guardar, la sucursal se propaga EN VIVO a la sesión.
    assert "aplicar_sucursal_activa(branch_id, branch_name)" in save_block
