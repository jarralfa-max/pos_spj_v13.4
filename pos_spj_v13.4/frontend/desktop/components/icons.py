"""Official icon catalog (FASE DS-3).

Icons are referenced by *semantic identifier*, never by inlined emoji. This keeps
the icon set uniform, theme-aware and swappable for an SVG/icon-font provider
later without touching call sites. Every icon also carries an accessible name.

Usage:
    from frontend.desktop.components.icons import Icons, icon_accessible_name
    button.setProperty("icon", Icons.ADD)
    button.setAccessibleName(icon_accessible_name(Icons.ADD))

The glyph mapping below is a transitional, centralized fallback (single place to
replace with real assets). Call sites must not hardcode emojis — the
``test_no_emoji_icons_in_new_frontend`` guardrail enforces this.
"""

from __future__ import annotations


class Icons:
    # module / domain
    PRODUCTS = "products"
    INVENTORY = "inventory"
    PRODUCTION = "production"
    PURCHASES = "purchases"
    SALES = "sales"
    CUSTOMERS = "customers"
    CASH = "cash"
    FINANCE = "finance"
    DELIVERY = "delivery"
    HR = "hr"
    SETTINGS = "settings"
    # actions
    ADD = "add"
    EDIT = "edit"
    DELETE = "delete"
    SEARCH = "search"
    REFRESH = "refresh"
    EXPORT = "export"
    PRINT = "print"
    CLOSE = "close"
    # status / feedback
    WARNING = "warning"
    SUCCESS = "success"
    ERROR = "error"
    INFO = "info"
    # fields
    CALENDAR = "calendar"
    CLOCK = "clock"
    PHONE = "phone"
    ADDRESS = "address"


#: Human, accessible names (es-MX) for screen readers / tooltips.
_ACCESSIBLE_NAMES = {
    Icons.PRODUCTS: "Productos", Icons.INVENTORY: "Inventario",
    Icons.PRODUCTION: "Producción", Icons.PURCHASES: "Compras",
    Icons.SALES: "Ventas", Icons.CUSTOMERS: "Clientes", Icons.CASH: "Caja",
    Icons.FINANCE: "Finanzas", Icons.DELIVERY: "Reparto", Icons.HR: "Recursos Humanos",
    Icons.SETTINGS: "Configuración", Icons.ADD: "Agregar", Icons.EDIT: "Editar",
    Icons.DELETE: "Eliminar", Icons.SEARCH: "Buscar", Icons.REFRESH: "Actualizar",
    Icons.EXPORT: "Exportar", Icons.PRINT: "Imprimir", Icons.CLOSE: "Cerrar",
    Icons.WARNING: "Advertencia", Icons.SUCCESS: "Éxito", Icons.ERROR: "Error",
    Icons.INFO: "Información", Icons.CALENDAR: "Calendario", Icons.CLOCK: "Hora",
    Icons.PHONE: "Teléfono", Icons.ADDRESS: "Dirección",
}


def icon_accessible_name(icon: str) -> str:
    """Return the es-MX accessible name for an icon identifier."""
    return _ACCESSIBLE_NAMES.get(icon, icon)


def all_icons() -> tuple[str, ...]:
    return tuple(_ACCESSIBLE_NAMES.keys())
