"""§49: el shell canónico y el legacy no pueden divergir más.

Estado real medido, no supuesto:

* `interfaz/main_window.py` registra **26** módulos vía `_conectar(...)` y es el
  único shell que el usuario ve — `main.py` lo construye directamente.
* `frontend/desktop/shell/desktop_shell_window_composition.py` cablea **10**
  módulos y **no lo llama ningún código productivo**: sólo pruebas. El shell
  canónico existe pero está DORMIDO.
* Los 10 canónicos tienen contraparte viva en MainWindow, así que esos dominios
  están compuestos dos veces. No son dos rutas vivas — la canónica no arranca —
  pero sí es el "existe pero no gobierna" que §49 declara hallazgo abierto.

Por qué este archivo es un ratchet y no un `assert` de corte:

Cambiar `main.py` al shell canónico hoy **perdería 16 módulos operativos**
(Activos, Delivery, Producción, BI, Mermas, WhatsApp…), y §2
prohíbe explícitamente eliminar funcionalidad operativa sin migración completa.
El corte exige migrar esos 16 primero. Mientras tanto, lo que sí se puede
garantizar es que la brecha **no crezca**: ningún módulo nuevo puede nacer en el
shell legacy, y el registro canónico no puede encoger.

Cuando un módulo migre, ambos conjuntos cambian y las pruebas de "no obsoleto"
obligan a actualizar este archivo — que es lo que convierte el corte en
inevitable en vez de perpetuo.
"""

from __future__ import annotations

import re

from .architecture_guardrails import APP_ROOT

_LEGACY_SHELL = APP_ROOT / "interfaz" / "main_window.py"
_CANONICAL_SHELL = (
    APP_ROOT / "frontend" / "desktop" / "shell" / "desktop_shell_window_composition.py"
)

# Módulos registrados por el shell legacy, medidos en ad155c2f. Puede ENCOGER
# (a medida que migran), nunca crecer.
_LEGACY_MODULES = frozenset({
    "ACTIVOS", "CAJA", "CLIENTES_CRM", "COMPRAS", "CONFIGURACION", "CONFIG_HARDWARE",
    "CONFIG_MODULOS", "CONFIG_SEGURIDAD", "COTIZACIONES", "DASHBOARD", "DELIVERY",
    "ETIQUETAS", "FINANZAS_UNIFICADAS", "GROWTH_ENGINE", "INTELIGENCIA_BI", "INVENTARIO",
    "MERMAS", "PLANEACION_COMPRAS", "POS", "PRODUCCION", "PRODUCTOS", "PROVEEDORES",
    "RRHH", "TARJETAS_FIDELIDAD", "TRANSFERENCIAS", "WHATSAPP",
})

# Identificadores cableados en el shell canónico. Puede CRECER, nunca encoger.
_CANONICAL_MODULE_IDS = frozenset({
    "SALES_POS_MODULE_ID", "CUSTOMERS_CRM_MODULE_ID", "FINANCE_MODULE_ID",
    "HR_MODULE_ID", "INVENTORY_MODULE_ID", "PRODUCTS_MODULE_ID",
    "PURCHASING_MODULE_ID", "TRANSFERS_MODULE_ID", "CASH_REGISTER_MODULE_ID",
    "CONFIGURACION_MODULE_ID",
})

# Correspondencia canónico -> slot legacy. Cuando un módulo complete su cutover,
# su entrada sale de `_LEGACY_MODULES` y de este mapa a la vez.
_CUTOVER_PAIRS = {
    "SALES_POS_MODULE_ID": "POS",
    "CUSTOMERS_CRM_MODULE_ID": "CLIENTES_CRM",
    "FINANCE_MODULE_ID": "FINANZAS_UNIFICADAS",
    "HR_MODULE_ID": "RRHH",
    "INVENTORY_MODULE_ID": "INVENTARIO",
    "PRODUCTS_MODULE_ID": "PRODUCTOS",
    "PURCHASING_MODULE_ID": "COMPRAS",
    "TRANSFERS_MODULE_ID": "TRANSFERENCIAS",
    "CASH_REGISTER_MODULE_ID": "CAJA",
    # `configuracion` ya tenía shell_registration.py completo y sólo faltaba
    # cablearlo. Cubre el slot CONFIGURACION; CONFIG_HARDWARE, CONFIG_MODULOS y
    # CONFIG_SEGURIDAD siguen siendo slots legacy propios hasta que el módulo
    # canónico absorba sus secciones.
    "CONFIGURACION_MODULE_ID": "CONFIGURACION",
}


def _legacy_modules() -> set[str]:
    source = _LEGACY_SHELL.read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r'_conectar\(\s*"([A-Z_]+)"', source))


def _canonical_module_ids() -> set[str]:
    source = _CANONICAL_SHELL.read_text(encoding="utf-8", errors="ignore")
    block = source[source.index("_MIGRATED_MODULE_WIRINGS"):]
    block = block[: block.index("\n)")]
    return set(re.findall(r"\b([A-Z_]+_MODULE_ID)\b", block))


def test_legacy_shell_does_not_gain_modules() -> None:
    """Ningún módulo nuevo puede nacer en el shell legacy."""
    added = _legacy_modules() - _LEGACY_MODULES
    assert not added, (
        "Módulos NUEVOS en el shell legacy (deben nacer en el canónico, §49):\n  "
        + "\n  ".join(sorted(added))
    )


def test_canonical_shell_does_not_lose_modules() -> None:
    """El registro canónico sólo puede crecer."""
    removed = _CANONICAL_MODULE_IDS - _canonical_module_ids()
    assert not removed, (
        "Módulos RETIRADOS del shell canónico — el cutover no puede retroceder:\n  "
        + "\n  ".join(sorted(removed))
    )


def test_cutover_progress_is_recorded() -> None:
    """Si un módulo migra, este archivo debe reflejarlo.

    Sin esta prueba el ratchet sólo impediría empeorar y el avance quedaría sin
    registrar — el fallo que `05_IDENTITY_GUARDRAILS.md` documenta cuando las
    allowlists conservaron deuda que ya no existía.
    """
    live_legacy = _legacy_modules()
    stale = _LEGACY_MODULES - live_legacy
    assert not stale, (
        "Estos módulos ya NO están en el shell legacy: retíralos de _LEGACY_MODULES "
        "y de _CUTOVER_PAIRS para dejar constancia del cutover:\n  "
        + "\n  ".join(sorted(stale))
    )

    grown = _canonical_module_ids() - _CANONICAL_MODULE_IDS
    assert not grown, (
        "Estos módulos ya están en el shell canónico: añádelos a "
        "_CANONICAL_MODULE_IDS (y empareja su slot legacy):\n  "
        + "\n  ".join(sorted(grown))
    )


def test_every_canonical_module_still_has_its_legacy_twin_documented() -> None:
    """Mientras un módulo esté en ambos shells, la duplicación queda explícita.

    Es el hallazgo §49 abierto: el mismo dominio compuesto dos veces. Que la
    canónica esté dormida no lo cierra.
    """
    assert set(_CUTOVER_PAIRS) == _CANONICAL_MODULE_IDS
    live_legacy = _legacy_modules()
    undocumented = {
        module_id: slot for module_id, slot in _CUTOVER_PAIRS.items() if slot not in live_legacy
    }
    assert not undocumented, (
        "El gemelo legacy de estos módulos desapareció: el cutover avanzó y hay que "
        "registrarlo aquí:\n  " + "\n  ".join(f"{k} -> {v}" for k, v in sorted(undocumented.items()))
    )


def test_remaining_cutover_gap_is_explicit() -> None:
    """La brecha real que bloquea las fases 5 y 6, medida y visible."""
    legacy_only = _legacy_modules() - set(_CUTOVER_PAIRS.values())
    assert len(legacy_only) == 16, (
        f"La brecha del cutover cambió: {len(legacy_only)} módulos sólo-legacy "
        f"(antes 16). Actualiza este número y 09_SHELL_CUTOVER_GAP.md:\n  "
        + "\n  ".join(sorted(legacy_only))
    )
