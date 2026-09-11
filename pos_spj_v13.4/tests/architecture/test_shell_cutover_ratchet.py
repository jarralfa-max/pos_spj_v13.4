"""§49 — el shell canónico y lo que quedó fuera de él.

LA PREMISA ANTERIOR SE ANULÓ, Y CONVIENE DEJARLA ESCRITA
---------------------------------------------------------
Este archivo medía la brecha entre dos shells: `interfaz/main_window.py`
registraba 26 módulos y era el único que el usuario veía, mientras
`desktop_shell_window_composition.py` cableaba 16 y no lo llamaba ningún código
productivo. El corte estaba prohibido porque perdería 10 módulos operativos, y
§2 no permite eliminar funcionalidad operativa sin migración completa.

El shell legacy ya no existe. Es decir: **el corte ocurrió por borrado, no por
migración** — exactamente el camino que este archivo existía para impedir. Sus
cuatro pruebas fallaban con `FileNotFoundError`, que no dice nada de eso.

Lo que sigue vivo de la pregunta original es lo que ahora se mide, y son dos
cosas distintas que conviene no mezclar:

  1. Módulos CONSTRUIDOS que no se pueden abrir. Una pantalla completa sin
     entrada de menú no falla nunca: simplemente no existe para el usuario, y
     el esfuerzo de construirla está parado en el aire.
  2. Módulos del shell anterior SIN reemplazo canónico. Eso es funcionalidad
     que el producto tenía y ya no tiene. No la borró esta suite y no le toca
     decidirlo, pero sí dejarla contada en vez de que se diluya.

Ambos conjuntos son trinquetes: sólo pueden ENCOGER. Si un módulo se cablea o
se reconstruye, la prueba de "sin entradas obsoletas" obliga a venir aquí a
quitarlo, que es lo que impide que el hueco se vuelva permanente por olvido.
"""

from __future__ import annotations

import os
import re

from .architecture_guardrails import APP_ROOT

_MODULES_DIR = APP_ROOT / "frontend" / "desktop" / "modules"
_NAVIGATION = (APP_ROOT / "frontend" / "desktop" / "shell" / "sidebar"
               / "migrated_modules_navigation.py")
_LEGACY_SHELL = APP_ROOT / "interfaz" / "main_window.py"

#: Construidos y sin entrada de menú, medidos hoy. `assets` tiene 12 archivos y
#: sólo `assets_routes.py`; `pricing` tiene 11 y un `navigation.py`/`routes.py`
#: propios — pero a ninguno de los dos le falta sólo la entrada: les falta el
#: `shell_registration.py` que el shell importa, como sí hace `inventory`.
_UNREACHABLE_MODULES = frozenset({"assets", "pricing"})

#: Módulos que el shell anterior ofrecía y que no tienen reemplazo canónico en
#: `frontend/desktop/modules/`. Comprobado uno a uno, no supuesto:
#:
#:   COTIZACIONES        sin módulo ni pantalla.
#:   ETIQUETAS           sin módulo ni pantalla.
#:   PLANEACION_COMPRAS  `PurchasePlanningQueryService` existe en el backend y
#:                       no tiene ni un consumidor (ver
#:                       test_no_forecast_sql_in_pyqt.py, que lo vigila con su
#:                       propio trinquete de hueco).
#:   WHATSAPP            no hay pantalla de escritorio. El microservicio
#:                       `whatsapp_service/` vive aparte y no la reemplaza: es
#:                       el backend del canal, no su administración.
#:
#: DASHBOARD no está en la lista a propósito: lo cubre
#: `business_intelligence/pages/executive_dashboard_page.py`.
_LOST_IN_RECONSTRUCTION = frozenset({
    "COTIZACIONES", "ETIQUETAS", "PLANEACION_COMPRAS", "WHATSAPP",
})


def _built_modules() -> set[str]:
    return {
        nombre for nombre in os.listdir(_MODULES_DIR)
        if (_MODULES_DIR / nombre).is_dir() and nombre != "__pycache__"
    }


def _navigable_modules() -> set[str]:
    return set(re.findall(r'item_id="nav\.([a-z_0-9]+)"',
                          _NAVIGATION.read_text(encoding="utf-8")))


# ── 1. nada nuevo puede nacer sin puerta ────────────────────────────────────
def test_no_module_is_built_without_a_way_to_open_it():
    """Construir una pantalla que nadie puede abrir no falla nunca.

    No hay excepción, no hay traza, no hay nada raro en los registros: el
    módulo simplemente no existe para el usuario. Este trinquete es lo único
    que distingue "todavía no se cableó" de "se olvidó".
    """
    huerfanos = _built_modules() - _navigable_modules() - _UNREACHABLE_MODULES
    assert not huerfanos, (
        "Módulos construidos sin entrada de menú y sin declarar:\n  "
        + "\n  ".join(sorted(huerfanos))
        + "\nSi es deliberado, añádelo a _UNREACHABLE_MODULES con su motivo; "
          "si no, cablea su `shell_registration.py` como hace `inventory`.")


def test_the_unreachable_list_has_no_stale_entries():
    """Cuando un módulo se cablea, su entrada aquí sobra — y retirarla es lo
    que hace que el trinquete baje en vez de quedarse quieto."""
    ya_navegables = sorted(_UNREACHABLE_MODULES & _navigable_modules())
    assert not ya_navegables, (
        f"Ya tienen entrada de menú, quítalos de _UNREACHABLE_MODULES: {ya_navegables}")

    inexistentes = sorted(_UNREACHABLE_MODULES - _built_modules())
    assert not inexistentes, (
        f"Ya no existen como módulo, quítalos de _UNREACHABLE_MODULES: {inexistentes}")


# ── 2. lo que el producto perdió, contado ───────────────────────────────────
def test_the_functionality_lost_in_the_reconstruction_is_an_explicit_list():
    """La pérdida se nombra, no se deduce.

    §2 prohíbe eliminar funcionalidad operativa sin migración completa. Aquí ya
    ocurrió, así que lo que queda por hacer es que no se diluya: cuatro nombres
    concretos, no "algunos módulos del shell anterior".
    """
    assert _LOST_IN_RECONSTRUCTION, (
        "La lista está vacía: o se reconstruyó todo —y entonces hay que retirar "
        "esta prueba— o alguien la vació sin reconstruir nada.")

    # Si alguno se reconstruyó, su nombre debe salir de la lista.
    construidos_equivalentes = {
        "COTIZACIONES": "quotes",
        "ETIQUETAS": "labels",
        "PLANEACION_COMPRAS": "purchase_planning",
        "WHATSAPP": "whatsapp",
    }
    resucitados = sorted(
        legacy for legacy, canonico in construidos_equivalentes.items()
        if legacy in _LOST_IN_RECONSTRUCTION and canonico in _built_modules()
    )
    assert not resucitados, (
        f"Ya tienen módulo canónico, quítalos de _LOST_IN_RECONSTRUCTION: {resucitados}")


# ── 3. el shell anterior no vuelve ──────────────────────────────────────────
def test_the_legacy_shell_does_not_come_back():
    """Reaparecer sería tener dos shells otra vez, y esta vez sin nadie
    midiendo la brecha: este archivo ya no la mide porque no la hay."""
    assert not _LEGACY_SHELL.exists(), (
        f"{_LEGACY_SHELL} volvió a existir. Si es deliberado, esta suite tiene "
        "que volver a medir la brecha entre los dos shells.")
