from pathlib import Path

from core.permissions import verificar_acceso_modulo

PERMISSIONS = Path("pos_spj_v13.4/core/permissions.py")


class _Session:
    is_active = True
    es_admin = False
    rol = "cajero"
    sucursal_nombre = "Principal"
    sucursal_id = 1
    usuario = "test"

    def __init__(self) -> None:
        self.requested = []

    def tiene_permiso(self, code: str) -> bool:
        self.requested.append(code)
        return code == "POS.ver"


class _Container:
    def __init__(self) -> None:
        self.session = _Session()


def test_module_access_asks_for_module_view_permission() -> None:
    container = _Container()

    assert verificar_acceso_modulo(container, "POS", None) is True
    assert container.session.requested == ["POS.ver"]


def test_module_access_source_has_no_legacy_module_map() -> None:
    content = PERMISSIONS.read_text(encoding="utf-8")
    assert "PERMISOS_MODULO" not in content
    assert "ventas.realizar" not in content
    assert "caja.abrir" not in content
    assert "config.editar" not in content
