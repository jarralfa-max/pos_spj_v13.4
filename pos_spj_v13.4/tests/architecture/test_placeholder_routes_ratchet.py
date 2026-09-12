"""§21 (PASS 4) — cuántas rutas de cada módulo llevan a una página real.

`NEW_ARCHITECTURE_RECOVERY_AUDIT.md` dejó esto pendiente: contó los tokens
(`Placeholder` en 33 archivos, `NotImplementedError` en 26, `mock` en 8) y
escribió "la clasificación es trabajo del PASS 4". Esto es esa clasificación,
puesta donde no se pueda quedar obsoleta.

LO QUE LA CLASIFICACIÓN ENCONTRÓ
---------------------------------
`NotImplementedError`: 31 apariciones, CERO huecos. Todas son contratos
abstractos (`ABC`/`Generic`), métodos plantilla cuyas subclases existen de
verdad —`_TransitionUseCase` tiene 45, `FinanceEventHandler` 19,
`FinanceFormDialog` 9— o guardas explícitas (un miembro de enum sin
implementación, el dialecto PostgreSQL). El único sin subclases,
`SlaughterExecutedStubHandler`, es una costura futura con `enabled = False`
que además NADIE suscribe.

`mock` importado en producción: cero. Eran 8 y se fueron con el legacy.

`Placeholder` como palabra: engañoso. De sus ~300 apariciones en la UI, la
inmensa mayoría son `placeholder=` y `setPlaceholderText`, que es el texto de
pista gris de un campo de captura y no tiene nada que ver con §21.

Lo que §21 sí señala, y es lo que se mide aquí: RUTAS DECLARADAS EN EL MENÚ DE
UN MÓDULO QUE RESUELVEN A UNA PÁGINA VACÍA. Una ruta así no falla: abre, se ve
ordenada, y no hace nada. El usuario no distingue "todavía no está construido"
de "está roto".

DÓNDE SE MIDE, Y POR QUÉ IMPORTA TANTO
---------------------------------------
NO se mide en `<módulo>_routes.py::build_page`. Medirlo ahí da CERO rutas reales
para `losses`, `meat_processing` y `orders_delivery`, y es falso: esos módulos
reciben un `page_builder` distinto desde su raíz de composición
(`losses_factory.py`, `meat_processing_factory.py`) o lo arman en la propia
vista a partir de `connection`/`branch_id` (`orders_delivery`). El
`build_page` del módulo es el respaldo, no la vía viva.

Es un error fácil de cometer —lo cometí al medir— y produce un número que
parece catastrófico y no lo es.
"""

from __future__ import annotations

import ast
import re

from .architecture_guardrails import APP_ROOT

#: `módulo -> (rutas con página real, rutas declaradas)`, medido hoy.
#: Los tres primeros coinciden con lo que sus propios docstrings afirman
#: (4/16, 1/29, 3/23), que es lo que da confianza en la medición.
#:
#: El primer número sólo puede SUBIR y el segundo sólo cambia cuando el módulo
#: declara rutas nuevas. Construir una página real y no actualizar esta tabla
#: hace fallar la prueba: es lo que convierte el relleno en visible en vez de
#: quedar enterrado en un docstring.
ROUTE_COVERAGE: dict[str, tuple[int, int]] = {
    "transfers": (15, 15),
    "configuracion": (11, 11),
    "business_intelligence": (12, 13),
    "pricing": (5, 6),
    "losses": (4, 16),
    "orders_delivery": (3, 23),
    "products": (2, 21),
    "meat_processing": (1, 29),
}

#: Dónde vive el `page_builder` VIVO de los módulos que no lo resuelven en su
#: propio `routes.py`. Sin esta indirección la medición da cero para los tres.
_LIVE_BUILDERS = {
    "losses": APP_ROOT / "backend/infrastructure/desktop/losses_factory.py",
    "meat_processing": APP_ROOT / "backend/infrastructure/desktop/meat_processing_factory.py",
}

_MODULES_DIR = APP_ROOT / "frontend" / "desktop" / "modules"


def _string_comparisons_in(path, function_name: str) -> set[str]:
    """Ids de ruta que la función distingue con un `==` o un `in (...)`.

    Estático a propósito: construir las páginas de verdad exigiría Qt, una
    conexión y una sesión por módulo, y la pregunta que se hace aquí —¿esta
    ruta tiene una rama propia?— se responde leyendo el código.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            ids: set[str] = set()
            for child in ast.walk(node):
                if not isinstance(child, ast.Compare):
                    continue
                for comparator in child.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                        ids.add(comparator.value)
                    elif isinstance(comparator, (ast.Tuple, ast.List, ast.Set)):
                        ids |= {
                            e.value for e in comparator.elts
                            if isinstance(e, ast.Constant) and isinstance(e.value, str)
                        }
            return ids
    return set()


def _dict_keys_in_source(path, dict_name: str) -> set[str]:
    """Claves de un diccionario de nivel de módulo, leídas del código."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == dict_name for t in node.targets):
            if isinstance(node.value, ast.Dict):
                return {
                    k.value for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
    return set()


#: Cada módulo resuelve sus páginas de una forma distinta, y son cuatro formas
#: DE VERDAD distintas. Fingir una sola regla es lo que produjo la primera
#: medición equivocada de este archivo (cero rutas reales en tres módulos).
#:
#:   factory        el `page_builder` vivo lo inyecta la raíz de composición;
#:                  el `routes.py` del módulo sólo devuelve placeholder.
#:   real_builders  un diccionario `_REAL_ROUTE_BUILDERS` nombra las rutas que
#:                  tienen constructor propio; el resto cae a placeholder.
#:   page_classes   `PAGE_CLASSES` mapea CADA ruta a una clase real.
#:   comparisons    `build_page` distingue con `if page_id == "..."`.
_STRATEGY = {
    "losses": ("factory", "backend/infrastructure/desktop/losses_factory.py"),
    "meat_processing": ("factory", "backend/infrastructure/desktop/meat_processing_factory.py"),
    "orders_delivery": ("real_builders", "orders_delivery_routes.py"),
    "business_intelligence": ("real_builders", "business_intelligence_routes.py"),
    "configuracion": ("page_classes", "pages/__init__.py"),
    "transfers": ("page_classes", "pages/__init__.py"),
    "pricing": ("comparisons", "routes.py"),
    "products": ("comparisons", "routes.py"),
}


def _real_routes(module: str) -> set[str]:
    """Rutas con página real. ESTÁTICO a propósito.

    La primera versión construía las páginas de verdad y las miraba. Funciona
    fuera de pytest y da los números correctos, pero DENTRO tumba el proceso
    con una violación de acceso —la misma que ya está documentada para los
    widgets de Qt en esta suite— y pytest ni llega a imprimir el nombre de la
    prueba. Una guardia que mata al que la ejecuta no protege nada.
    """
    forma, donde = _STRATEGY[module]

    if forma == "factory":
        return _string_comparisons_in(APP_ROOT / donde, "page_builder")

    if forma == "real_builders":
        source = (_MODULES_DIR / module / donde).read_text(encoding="utf-8")
        bloque = source.split("_REAL_ROUTE_BUILDERS")[1].split("}")[0]
        return set(re.findall(r'"([a-z_0-9]+)"\s*:', bloque))

    if forma == "page_classes":
        # Se IMPORTA en vez de leerse: `PAGE_CLASSES` es una comprensión
        # (`{page.page_id: page for page in (...)}`), no un diccionario
        # literal, así que sus claves no están escritas en el código. Importar
        # es seguro —son clases de widget, no instancias— y sólo instanciarlas
        # sin `QApplication` tumbaría el proceso.
        import importlib

        mod = importlib.import_module(f"frontend.desktop.modules.{module}.pages")
        reales = set(getattr(mod, "PAGE_CLASSES", {}))
        # `transfers` resuelve dos rutas fuera del diccionario, con un `if`.
        return reales | _string_comparisons_in(
            _MODULES_DIR / module / f"{module}_routes.py", "build_page")

    return _string_comparisons_in(_MODULES_DIR / module / donde, "build_page")


def _modules_with_a_page_builder() -> set[str]:
    """Sólo los que resuelven páginas. Tener un `*_routes.py` no basta: siete
    módulos lo usan sólo como modelo de navegación (`visible_routes`/
    `grouped_routes`) y construyen sus páginas en el propio espacio de trabajo.
    """
    import importlib

    encontrados = set()
    for carpeta in _MODULES_DIR.iterdir():
        if not carpeta.is_dir() or carpeta.name == "__pycache__":
            continue
        if carpeta.name in _LIVE_BUILDERS or carpeta.name == "orders_delivery":
            encontrados.add(carpeta.name)
            continue
        for sufijo in (f"{carpeta.name}_routes", "routes"):
            try:
                mod = importlib.import_module(
                    f"frontend.desktop.modules.{carpeta.name}.{sufijo}")
            except Exception:
                continue
            if hasattr(mod, "build_page"):
                encontrados.add(carpeta.name)
                break
    return encontrados


# ── el trinquete ────────────────────────────────────────────────────────────
def test_no_module_loses_real_pages():
    """Una ruta que tenía página real y vuelve a ser placeholder es una
    regresión invisible: la pantalla sigue abriendo."""
    retrocesos = []
    for module, (esperadas, _total) in sorted(ROUTE_COVERAGE.items()):
        reales = len(_real_routes(module))
        if reales < esperadas:
            retrocesos.append(f"{module}: {reales} reales, se esperaban {esperadas}")
    assert not retrocesos, "Módulos que perdieron páginas reales:\n  " + "\n  ".join(retrocesos)


def test_new_real_pages_are_recorded():
    """Al revés: construir una página y no anotarlo aquí también falla.

    Sin esto la tabla envejece en silencio y deja de decir nada — que es
    exactamente cómo el conteo del PASS 1 llegó a estar tres pases desfasado.
    """
    sin_anotar = []
    for module, (esperadas, _total) in sorted(ROUTE_COVERAGE.items()):
        reales = len(_real_routes(module))
        if reales > esperadas:
            sin_anotar.append(f"{module}: ahora hay {reales} reales, la tabla dice {esperadas}")
    assert not sin_anotar, (
        "Sube el contador en ROUTE_COVERAGE (el trinquete sólo crece):\n  "
        + "\n  ".join(sin_anotar))


def test_the_table_has_no_stale_modules():
    existentes = {
        p.name for p in _MODULES_DIR.iterdir()
        if p.is_dir() and p.name != "__pycache__"
    }
    fantasmas = sorted(set(ROUTE_COVERAGE) - existentes)
    assert not fantasmas, f"Módulos que ya no existen: {fantasmas}"


def test_every_module_with_a_router_is_measured():
    """Un módulo nuevo no puede entrar sin que se sepa cuánto de él es real."""
    sin_medir = sorted(_modules_with_a_page_builder() - set(ROUTE_COVERAGE))
    assert not sin_medir, (
        "Módulos con enrutador y sin medir en ROUTE_COVERAGE: "
        f"{sin_medir}")


def test_the_measurement_does_not_read_the_fallback_builder():
    """La prueba que protege a la propia medición.

    `losses_routes.build_page` devuelve placeholder para TODAS sus rutas; las 4
    reales sólo aparecen si se lee el `page_builder` de `losses_factory.py`.
    Si alguien "simplificara" `_real_routes` para leer siempre el `routes.py`
    del módulo, el número caería a cero y parecería una regresión enorme que no
    ocurrió.
    """
    assert _string_comparisons_in(
        _MODULES_DIR / "losses" / "losses_routes.py", "build_page") == set(), (
        "`losses_routes.build_page` ya distingue rutas: revisa si sigue siendo "
        "el respaldo o pasó a ser la vía viva.")
    assert len(_real_routes("losses")) == 4
