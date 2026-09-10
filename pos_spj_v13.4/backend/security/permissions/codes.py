"""Formato canónico de los códigos de permiso: ``MODULO.accion``.

Este módulo es deliberadamente **puro**: sin base de datos, sin sesión, sin
importar ninguna otra capa. Es el vocabulario compartido por el catálogo
(`backend/application/security/permission_catalog.py`), por el evaluador del
arranque (`backend/bootstrap/permission_evaluator.py`), por cada
`permissions.py` de contexto acotado y por los registros de menú del shell.
Al no depender de nada, puede colgar de `backend/security/` sin invertir la
dirección de las dependencias: quien agrega vocabulario vive más arriba.

El almacenamiento es la tabla `rol_permisos(rol_id, modulo, accion, permitido)`
— módulo y acción en columnas separadas — mientras que el código que las UI y
los casos de uso manejan es la forma punteada `MODULO.accion`. Estas tres
funciones son el único puente entre ambas formas.

ATENCIÓN — la asimetría entre `permission_code()` y `normalize_permission()`
es intencional y es la trampa principal de este módulo:

    permission_code("pos", "VER")   -> "POS.ver"    (módulo MAYÚS, acción minús)
    normalize_permission("pos.ver") -> "POS.VER"    (TODO en mayúsculas)

`permission_code()` produce la forma *de almacenamiento y presentación*, que
es la que se guarda en `rol_permisos` y la que se lee en la matriz de
permisos. `normalize_permission()` produce la forma *de comparación*, que
existe sólo para que el cotejo sea insensible a mayúsculas.

De ahí se sigue una regla que no es opcional: **cualquier conjunto de permisos
que vaya a compararse con `normalize_permission()` tiene que haber pasado
también por `normalize_permission()`**. `PermissionEvaluator` hace
`normalize_permission(code) in context.permissions`; si `permissions` se
cargara en la forma de `permission_code()` ("POS.ver") y la consulta llegara
normalizada ("POS.VER"), *ningún* permiso coincidiría jamás y el sistema
denegaría todo en silencio. Por eso `PermissionQueryService` normaliza al
cargar. Ver el test que fija este contrato en
`tests/architecture/test_permission_codes_contract.py`.
"""
from __future__ import annotations

#: Separador entre módulo y acción. La acción puede contener más puntos
#: ("valor.aprobar"), así que sólo el PRIMER punto separa módulo de acción.
SEPARATOR = "."

#: Acción de lectura/apertura de un módulo. Es la que el shell exige para
#: mostrar una entrada de menú (`MODULO.ver`).
VIEW_ACTION = "ver"

#: Comodines reconocidos por el evaluador: `*` global y `MODULO.*` por módulo.
WILDCARD = "*"


def permission_code(module: str, action: str) -> str:
    """Forma canónica de almacenamiento: ``MODULO.accion``.

    El módulo se normaliza a MAYÚSCULAS y la acción a minúsculas, de modo que
    `permission_code("pos", "VER")` y `permission_code("POS", "ver")` produzcan
    el mismo código y no puedan nacer dos filas distintas en `rol_permisos`
    para el mismo permiso.
    """
    return f"{module.strip().upper()}{SEPARATOR}{action.strip().lower()}"


def module_view_permission(module: str) -> str:
    """Permiso de apertura de un módulo — `MODULO.ver`.

    Es el que consulta el shell para decidir si una entrada del menú lateral
    es visible, y el único permiso que un módulo puede exigir sólo para
    abrirse: cada acción sensible dentro del módulo tiene su propio código.
    """
    return permission_code(module, VIEW_ACTION)


def normalize_permission(code: str) -> str:
    """Forma canónica de COMPARACIÓN — todo en mayúsculas.

    No es la forma de almacenamiento (ver el aviso del docstring del módulo).
    Sólo debe usarse para cotejar, y siempre en ambos lados del cotejo.
    """
    return code.strip().upper()


def split_permission(code: str) -> tuple[str, str]:
    """Divide ``MODULO.accion`` en `(MODULO, accion)` para escribir en
    `rol_permisos`, que guarda módulo y acción en columnas separadas.

    Sólo separa por el primer punto: las acciones compuestas
    ("valor.aprobar", "forecast.modelo.aprobar") son una sola acción, no una
    jerarquía de módulos. Un código sin punto no tiene módulo y devuelve
    `("", codigo)` — es el caso de los códigos planos heredados
    (`TRANSFERS_APPROVE`), que nunca llegaron a adoptar este formato.
    """
    module, sep, action = code.strip().partition(SEPARATOR)
    if not sep:
        return "", code.strip()
    return module.upper(), action.lower()
