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
    HOME = "home"
    CHEVRON_LEFT = "chevron_left"
    CHEVRON_RIGHT = "chevron_right"
    CHEVRON_DOWN = "chevron_down"
    USER = "user"
    LOGOUT = "logout"
    LOCK = "lock"
    FILE = "file"
    CHECK = "check"
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
    TRANSFERS = "transfers"
    LOYALTY = "loyalty"
    LOYALTY_CARDS = "loyalty_cards"
    ASSETS = "assets"
    MAINTENANCE = "maintenance"
    ANALYTICS = "analytics"
    # actions
    ADD = "add"
    EDIT = "edit"
    DELETE = "delete"
    SEARCH = "search"
    REFRESH = "refresh"
    EXPORT = "export"
    PRINT = "print"
    CLOSE = "close"
    NOTIFICATIONS = "notifications"
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
    KEYBOARD = "keyboard"
    NUMERIC_KEYPAD = "numeric_keypad"


#: Human, accessible names (es-MX) for screen readers / tooltips.
_ACCESSIBLE_NAMES = {
    Icons.HOME: "Inicio", Icons.CHEVRON_LEFT: "Contraer",
    Icons.CHEVRON_RIGHT: "Expandir", Icons.CHEVRON_DOWN: "Desplegar",
    Icons.USER: "Usuario", Icons.LOGOUT: "Cerrar sesión", Icons.LOCK: "Bloquear sesión",
    Icons.FILE: "Archivo", Icons.CHECK: "Confirmar",
    Icons.PRODUCTS: "Productos", Icons.INVENTORY: "Inventario",
    Icons.PRODUCTION: "Producción", Icons.PURCHASES: "Compras",
    Icons.SALES: "Ventas", Icons.CUSTOMERS: "Clientes", Icons.CASH: "Caja",
    Icons.FINANCE: "Finanzas", Icons.DELIVERY: "Reparto", Icons.HR: "Recursos Humanos",
    Icons.SETTINGS: "Configuración", Icons.TRANSFERS: "Transferencias",
    Icons.LOYALTY: "Fidelización", Icons.LOYALTY_CARDS: "Tarjetas de fidelidad",
    Icons.ASSETS: "Activos", Icons.MAINTENANCE: "Mantenimiento",
    Icons.ANALYTICS: "Inteligencia de Negocios",
    Icons.ADD: "Agregar", Icons.EDIT: "Editar",
    Icons.DELETE: "Eliminar", Icons.SEARCH: "Buscar", Icons.REFRESH: "Actualizar",
    Icons.EXPORT: "Exportar", Icons.PRINT: "Imprimir", Icons.CLOSE: "Cerrar",
    Icons.NOTIFICATIONS: "Notificaciones",
    Icons.WARNING: "Advertencia", Icons.SUCCESS: "Éxito", Icons.ERROR: "Error",
    Icons.INFO: "Información", Icons.CALENDAR: "Calendario", Icons.CLOCK: "Hora",
    Icons.PHONE: "Teléfono", Icons.ADDRESS: "Dirección",
    Icons.KEYBOARD: "Mostrar teclado en pantalla",
    Icons.NUMERIC_KEYPAD: "Mostrar teclado numerico",
}


def icon_accessible_name(icon: str) -> str:
    """Return the es-MX accessible name for an icon identifier."""
    return _ACCESSIBLE_NAMES.get(icon, icon)


def all_icons() -> tuple[str, ...]:
    return tuple(_ACCESSIBLE_NAMES.keys())


# Native vector assets: the paths describe interface symbols, never brand logos.
_PATHS = {
    "home": '<path d="M3 10 12 3l9 7v11h-6v-7H9v7H3Z"/>',
    "chevron_left": '<path d="m15 5-7 7 7 7"/>',
    "chevron_right": '<path d="m9 5 7 7-7 7"/>',
    "chevron_down": '<path d="m5 9 7 7 7-7"/>',
    "user": '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/>',
    "add": '<path d="M12 4v16M4 12h16"/>',
    "edit": '<path d="m15 4 5 5M3 21l2-7L17 2l5 5-12 12Z"/>',
    "delete": '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
    "search": '<circle cx="10" cy="10" r="7"/><path d="m15 15 6 6"/>',
    "refresh": '<path d="M20 8a9 9 0 1 0 0 9M20 2v6h-6"/>',
    "export": '<path d="M12 16V2m-5 5 5-5 5 5M3 14v7h18v-7"/>',
    "print": '<path d="M6 8V2h12v6M6 17H2V8h20v9h-4M6 14h12v8H6Z"/>',
    "close": '<path d="m5 5 14 14M5 19 19 5"/>',
    "notifications": '<path d="M5 10a7 7 0 0 1 14 0v6l2 3H3l2-3ZM9 22h6"/>',
    "warning": '<path d="m12 2 10 19H2ZM12 8v6m0 3v1"/>',
    "success": '<circle cx="12" cy="12" r="10"/><path d="m6 12 4 4 8-8"/>',
    "error": '<circle cx="12" cy="12" r="10"/><path d="m8 8 8 8m-8 0 8-8"/>',
    "info": '<circle cx="12" cy="12" r="10"/><path d="M12 10v8m0-13v2"/>',
    "calendar": '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M3 10h18M7 2v5m10-5v5"/>',
    "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 5v7l5 3"/>',
    "phone": '<path d="m5 2 4 5-3 3a17 17 0 0 0 8 8l3-3 5 4c-5 10-25-10-17-17Z"/>',
    "address": '<path d="M12 22S4 14 4 9a8 8 0 0 1 16 0c0 5-8 13-8 13Z"/><circle cx="12" cy="9" r="3"/>',
    "keyboard": '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M5 9h2m2 0h2m2 0h2m2 0h2M5 13h2m2 0h2m2 0h2m2 0h2M6 16h12"/>',
    "products": '<path d="m12 2 10 5v10l-10 5-10-5V7Zm-10 5 10 5 10-5M12 12v10M7 4l10 5"/>',
    "inventory": '<path d="M2 9 12 2l10 7v13H2ZM6 22V11h12v11M6 15h12M6 19h12"/>',
    "production": '<path d="M2 22V10l7 4V7l7 7V2h6v20ZM6 18h2m4 0h2m4 0h2"/>',
    "purchases": '<path d="M2 3h3l3 13h11l3-10H6"/><circle cx="9" cy="21" r="1"/><circle cx="19" cy="21" r="1"/>',
    "sales": '<path d="M4 2h16v20l-4-2-4 2-4-2-4 2ZM8 7h8M8 11h8M8 15h5"/>',
    "cash": '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="12" cy="12" r="4"/><path d="M5 12h1m12 0h1"/>',
    "finance": '<path d="m2 8 10-6 10 6ZM2 22h20M4 10v9m5-9v9m6-9v9m5-9v9"/>',
    "delivery": '<path d="M1 4h13v14H1ZM14 9h5l4 5v4h-9"/><circle cx="6" cy="19" r="3"/><circle cx="18" cy="19" r="3"/>',
    "settings": '<circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="3"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4M4 4l3 3m10 10 3 3M4 20l3-3M17 7l3-3"/>',
    "transfers": '<path d="M2 7h19m-5-5 5 5-5 5M22 17H3m5-5-5 5 5 5"/>',
    "loyalty": '<path d="M12 21 3 12C-3 4 7-1 12 6c5-7 15-2 9 6Z"/>',
    "loyalty_cards": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="M2 9h20M5 15h5"/>',
    "assets": '<rect x="2" y="7" width="20" height="15" rx="2"/><path d="M8 7V2h8v5M2 12h20M9 12v3h6v-3"/>',
    "maintenance": '<path d="M14 3a6 6 0 0 0-5 9L2 19l3 3 7-7a6 6 0 0 0 9-7l-4 4-5-5 4-4Z"/>',
    "analytics": '<path d="M2 2v20h20M6 17v-6m5 6V5m5 12V9m5 8V3"/>',
    "logout": '<path d="M10 3H3v18h7M8 12h14m-5-5 5 5-5 5"/>',
    "lock": '<rect x="4" y="10" width="16" height="12" rx="2"/><path d="M7 10V6a5 5 0 0 1 10 0v4M12 15v3"/>',
    "file": '<path d="M4 2h10l6 6v14H4ZM14 2v6h6M8 13h8m-8 4h8"/>',
    "check": '<path d="m3 12 6 6L21 5"/>',
}
_PATHS[Icons.CUSTOMERS] = _PATHS[Icons.USER]
_PATHS[Icons.HR] = _PATHS[Icons.USER]
_PATHS[Icons.NUMERIC_KEYPAD] = _PATHS[Icons.KEYBOARD]


class IconProvider:
    """Canonical SVG renderer with semantic colors and native QIcon modes."""

    @classmethod
    def icon(cls, name: str, *, size: int = 20, state: str = "normal", theme=None):
        from PyQt5.QtCore import QByteArray, Qt
        from PyQt5.QtGui import QIcon, QPainter, QPixmap
        from PyQt5.QtSvg import QSvgRenderer
        from frontend.desktop.themes.theme_manager import ThemeManager
        from frontend.desktop.themes.semantic_colors import SemanticColors

        colors = SemanticColors.for_theme(theme or ThemeManager.instance().theme)
        color = {
            "normal": colors.TEXT_SECONDARY, "hover": colors.PRIMARY_DEFAULT,
            "selected": colors.PRIMARY_DEFAULT, "disabled": colors.TEXT_DISABLED,
            "danger": colors.DANGER_DEFAULT, "success": colors.SUCCESS_DEFAULT,
            "warning": colors.WARNING_DEFAULT,
        }.get(state, colors.TEXT_SECONDARY)
        path = _PATHS.get(name, _PATHS[Icons.FILE])
        icon = QIcon()
        for mode, stroke in ((QIcon.Normal, color), (QIcon.Active, colors.PRIMARY_DEFAULT),
                             (QIcon.Selected, colors.PRIMARY_DEFAULT),
                             (QIcon.Disabled, colors.TEXT_DISABLED)):
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                   f'fill="none" stroke="{stroke}" stroke-width="1.8" '
                   f'stroke-linecap="round" stroke-linejoin="round">{path}</svg>')
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            for pixels in (size, size * 2):
                pixmap = QPixmap(pixels, pixels)
                pixmap.fill(Qt.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                icon.addPixmap(pixmap, mode)
        return icon

    @classmethod
    def bind(cls, widget, name: str, *, size: int = 20, state: str = "normal"):
        """Keep a button/action icon current without retaining deleted widgets."""
        from PyQt5.QtCore import QObject, QSize
        from frontend.desktop.themes.theme_manager import ThemeManager

        class Binding(QObject):
            def refresh(self, _theme=None):
                widget.setIcon(cls.icon(name, size=size, state=state))

        previous = getattr(widget, "_spj_icon_binding", None)
        if previous is not None:
            ThemeManager.instance().theme_changed.disconnect(previous.refresh)
            previous.deleteLater()
        binding = Binding(widget)
        widget._spj_icon_binding = binding
        widget.setProperty("icon", name)
        if hasattr(widget, "setIconSize"):
            widget.setIconSize(QSize(size, size))
        binding.refresh()
        ThemeManager.instance().theme_changed.connect(binding.refresh)
        return binding
