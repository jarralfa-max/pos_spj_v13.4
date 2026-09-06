"""§49: el shell canónico y el legacy no pueden divergir más.

Estado real medido, no supuesto:

* `interfaz/main_window.py` registra **26** módulos vía `_conectar(...)` y es el
  único shell que el usuario ve — `main.py` lo construye directamente.
* `frontend/desktop/shell/desktop_shell_window_composition.py` cablea **16**
  módulos y **no lo llama ningún código productivo**: sólo pruebas. El shell
  canónico existe pero está DORMIDO.
* Los 16 canónicos tienen contraparte viva en MainWindow, así que esos dominios
  están compuestos dos veces. No son dos rutas vivas — la canónica no arranca —
  pero sí es el "existe pero no gobierna" que §49 declara hallazgo abierto.

Por qué este archivo es un ratchet y no un `assert` de corte:

Cambiar `main.py` al shell canónico hoy **perdería 10 módulos operativos**
(Activos, Proveedores, Etiquetas, WhatsApp, Cotizaciones…), y §2
prohíbe explícitamente eliminar funcionalidad operativa sin migración completa.
El corte exige migrar esos 10 primero. Mientras tanto, lo que sí se puede
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
    "CONFIGURACION_MODULE_ID", "BUSINESS_INTELLIGENCE_MODULE_ID",
    "LOSSES_MODULE_ID", "MEAT_PROCESSING_MODULE_ID", "ORDERS_DELIVERY_MODULE_ID",
    "FIDELIDAD_MODULE_ID", "TARJETAS_FIDELIDAD_MODULE_ID",
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
    # `business_intelligence` construye páginas reales en 10 de sus 13 rutas
    # (`_REAL_ROUTE_BUILDERS`); las 3 restantes caen a placeholder explícito.
    "BUSINESS_INTELLIGENCE_MODULE_ID": "INTELIGENCIA_BI",
    # Cableados por decisión explícita del usuario sabiendo que su contenido
    # todavía es parcial o placeholder; ver _PLACEHOLDER_BACKED.
    "LOSSES_MODULE_ID": "MERMAS",
    "MEAT_PROCESSING_MODULE_ID": "PRODUCCION",
    "ORDERS_DELIVERY_MODULE_ID": "DELIVERY",
    "FIDELIDAD_MODULE_ID": "GROWTH_ENGINE",
    "TARJETAS_FIDELIDAD_MODULE_ID": "TARJETAS_FIDELIDAD",
}

# Módulos cableados al shell canónico cuyo contenido es total o mayoritariamente
# placeholder. Están aquí por decisión explícita del usuario ("cablealos, en otra
# sesión se corregirán los módulos"), no por descuido.
#
# Mientras esta lista no esté vacía, `main.py` NO puede cortar al shell canónico:
# hacerlo convertiría estas pantallas en relleno para el usuario final. La prueba
# `test_main_is_not_cut_over_while_placeholder_modules_are_wired` lo impide.
_PLACEHOLDER_BACKED = {
    "LOSSES_MODULE_ID": "todas sus rutas devuelven LossesPlaceholderPage",
    "MEAT_PROCESSING_MODULE_ID": "todas sus rutas devuelven MeatProcessingPlaceholderPage",
    "ORDERS_DELIVERY_MODULE_ID": "20 de 23 rutas son placeholder (3 reales)",
    "FIDELIDAD_MODULE_ID": "parte de sus páginas son placeholder",
    "TARJETAS_FIDELIDAD_MODULE_ID": "parte de sus páginas son placeholder",
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
    assert len(legacy_only) == 10, (
        f"La brecha del cutover cambió: {len(legacy_only)} módulos sólo-legacy "
        f"(antes 10). Actualiza este número y 09_SHELL_CUTOVER_GAP.md:\n  "
        + "\n  ".join(sorted(legacy_only))
    )


def test_main_is_not_cut_over_while_placeholder_modules_are_wired() -> None:
    """`main.py` no puede cortar al shell canónico con módulos placeholder dentro.

    Los cinco módulos de `_PLACEHOLDER_BACKED` se cablearon a propósito para que
    el shell nuevo quede completo estructuralmente, con el contenido pendiente
    para una sesión posterior. Eso es seguro **sólo mientras el shell siga
    dormido**: si `main.py` corta ahora, Mermas, Producción y Delivery pasan a
    ser pantallas de relleno para el usuario final, que es justo lo que §2
    prohíbe.

    Esta prueba es el pestillo: o se rellenan las páginas y se vacía
    `_PLACEHOLDER_BACKED`, o `main.py` no corta. Falla en cuanto alguien intente
    lo segundo sin lo primero.
    """
    if not _PLACEHOLDER_BACKED:
        return  # ya no hay placeholders: el corte deja de estar bloqueado por esto

    main_source = (APP_ROOT / "main.py").read_text(encoding="utf-8", errors="ignore")
    cutover_markers = ("build_application_window", "ApplicationWindow", "CompositionRoot")
    used = [marker for marker in cutover_markers if marker in main_source]
    detail = "; ".join(
        f"{module}: {reason}" for module, reason in sorted(_PLACEHOLDER_BACKED.items())
    )
    assert not used, (
        "main.py está cortando al shell canónico, pero siguen cableados módulos con "
        "contenido placeholder — el usuario final vería pantallas de relleno. "
        f"Pendientes: {detail}. Marcadores encontrados en main.py: {used}"
    )
