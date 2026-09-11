"""La matriz de permisos parte del catálogo, no de lo que haya en la tabla.

QUÉ FIJABA ESTA PRUEBA Y POR QUÉ IMPORTA
-----------------------------------------
La pantalla de Roles muestra una matriz de módulos × acciones para marcar
permisos. Si esa matriz se construyera leyendo sólo `rol_permisos`, una
instalación recién creada —donde esa tabla está vacía— mostraría una matriz
VACÍA: ni un módulo que marcar. No es un error, es una pantalla en blanco que
parece que el sistema no tiene permisos que conceder, y deja al administrador
sin forma de conceder el primero.

Por eso la matriz debe partir del CATÁLOGO de permisos y superponerle lo que la
tabla diga.

POR QUÉ ES UN TRINQUETE DE HUECO Y NO UNA PRUEBA NORMAL
-------------------------------------------------------
Su sujeto era `repositories/config_repository.py::ConfigRepository
.permission_matrix()`, borrado con toda la carpeta. Y no hay reemplazo:

  · `PermissionMatrixDTO` existe en
    `backend/application/dto/configuracion_dtos.py` y NADIE lo construye —
    cero productores, cero consumidores.
  · `CANONICAL_MODULE_PERMISSIONS` (el catálogo) no tiene ni un importador de
    producción: sólo lo leen las guardias de `tests/architecture/`.
  · `frontend/desktop/modules/configuracion/pages/usuarios_roles_page.py` lo
    dice en su propia cabecera: gestiona roles "NOT the permission matrix".

Así que la conducta no está cubierta en otro sitio: falta entera. Escrita como
`xfail(strict=True)`, el día que alguien construya la matriz esta prueba
empezará a pasar, pytest lo reportará como XPASS —que con strict es un fallo— y
tendrá que venir a quitar el marcador. El hueco no se cierra en silencio.
"""

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HUECO CONOCIDO: no existe una matriz de permisos canónica. "
        "`PermissionMatrixDTO` no tiene productores y el catálogo "
        "`CANONICAL_MODULE_PERMISSIONS` no tiene consumidores de producción. "
        "Mientras siga así, la pantalla de Roles no puede reemplazar a la "
        "legacy. Cuando se construya, quita este marcador."
    ),
)
def test_permission_matrix_includes_catalog_when_role_permissions_empty() -> None:
    from backend.application.security.permission_catalog import (
        CANONICAL_MODULE_PERMISSIONS,
    )

    constructor = _find_matrix_builder()
    assert constructor is not None, (
        "Nada construye una matriz de permisos: la pantalla de Roles no puede "
        "mostrar módulos que marcar en una instalación recién creada.")

    # Con `rol_permisos` vacía, la matriz debe traer igualmente el catálogo.
    matriz = constructor(role_permissions={})
    for modulo in ("POS", "CAJA", "CONFIG_SEGURIDAD"):
        assert modulo in matriz, f"el catálogo no aporta {modulo}"
        assert "ver" in matriz[modulo]
        assert set(matriz[modulo]) >= set(CANONICAL_MODULE_PERMISSIONS.get(modulo, ()))


def _find_matrix_builder():
    """El constructor canónico de la matriz, si alguien lo escribió.

    Se busca en vez de importarse a ciegas porque todavía no existe: un import
    directo haría fallar la recolección del archivo entero, que es como esta
    prueba llevaba rota — un `ModuleNotFoundError` que no dice nada del hueco
    que en realidad documenta.
    """
    try:
        from backend.application.configuracion import (  # noqa: F401
            permission_matrix_query,
        )
    except ImportError:
        return None
    return getattr(permission_matrix_query, "build_permission_matrix", None)
