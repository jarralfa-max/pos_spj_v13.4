"""Official icon catalog (FASE DS-3).

Icons are referenced by *semantic identifier*, never by inlined emoji. This keeps
the icon set uniform and theme-aware. Every icon also carries an accessible name.

Usage:
    from frontend.desktop.components.icons import Icons, IconProvider
    IconProvider.bind(button, Icons.ADD)

IconProvider renders the canonical vector paths into native QIcons and refreshes
bound controls when the theme changes. Call sites must not hardcode glyphs.
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
    # Navigation concepts already requested by the enterprise modules.
    ACTIVITY = "activity"
    ADJUSTMENT = "adjustment"
    ALERT = "alert"
    ANIMAL_LOT = "animal_lot"
    APPROVAL = "approval"
    AUDIT = "audit"
    BARCODE = "barcode"
    BELL = "bell"
    BRANCH = "branch"
    BUNDLE = "bundle"
    CARCASS = "carcass"
    CATALOG = "catalog"
    CATEGORY = "category"
    CHART = "chart"
    CHECKLIST = "checklist"
    COLD = "cold"
    COMPANY = "company"
    CONDEMN = "condemn"
    COST = "cost"
    COUNT = "count"
    CUT = "cut"
    CUTTING = "cutting"
    DASHBOARD = "dashboard"
    DERIVED = "derived"
    DEVICE = "device"
    DIFFERENCE = "difference"
    DISPATCH = "dispatch"
    DISPLAY = "display"
    DISPOSAL = "disposal"
    DOCUMENT = "document"
    DRIVER = "driver"
    EXPIRY = "expiry"
    EXTERNAL = "external"
    FAILED = "failed"
    FLAG = "flag"
    FORECAST = "forecast"
    GRADE = "grade"
    IMPORT = "import"
    INCIDENT = "incident"
    INSPECTION = "inspection"
    INTEGRATION = "integration"
    INTERNAL = "internal"
    INVESTIGATION = "investigation"
    KITCHEN = "kitchen"
    LIST = "list"
    LOCATION = "location"
    LOT = "lot"
    LOTS = "lots"
    MATERIAL = "material"
    MEAT = "meat"
    MOVEMENTS = "movements"
    OFFLINE = "offline"
    ORDERS = "orders"
    PACKAGE = "package"
    PENDING = "pending"
    PICKING = "picking"
    PICKUP = "pickup"
    PRICE = "price"
    PURCHASE = "purchase"
    QUALITY = "quality"
    RECEIPT = "receipt"
    RECEIVING = "receiving"
    RECIPE = "recipe"
    RECOMMENDATION = "recommendation"
    RECOVERY = "recovery"
    REDO = "redo"
    REPLENISHMENT = "replenishment"
    REPORT = "report"
    REQUEST = "request"
    RESERVATION = "reservation"
    RETURN = "return"
    REWORK = "rework"
    ROUTE = "route"
    SCALE = "scale"
    SCENARIO = "scenario"
    SCHEDULE = "schedule"
    SETTLEMENT = "settlement"
    SPECIES = "species"
    SUGGESTION = "suggestion"
    SUPPLIER = "supplier"
    TASKS = "tasks"
    TEMPERATURE = "temperature"
    THEME = "theme"
    TRACE = "trace"
    TRACEABILITY = "traceability"
    TRACKING = "tracking"
    TRANSFER = "transfer"
    TRANSIT = "transit"
    UNIT = "unit"
    USERS = "users"
    WAREHOUSE = "warehouse"
    WASTE = "waste"
    YIELD = "yield"


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
    Icons.NUMERIC_KEYPAD: "Mostrar teclado numérico",
    Icons.ACTIVITY: "Actividad", Icons.ADJUSTMENT: "Ajustes", Icons.ALERT: "Alerta",
    Icons.ANIMAL_LOT: "Lote de animales", Icons.APPROVAL: "Aprobación", Icons.AUDIT: "Auditoría",
    Icons.BARCODE: "Código de barras", Icons.BELL: "Notificaciones", Icons.BRANCH: "Sucursal",
    Icons.BUNDLE: "Paquete de productos", Icons.CARCASS: "Canal cárnica", Icons.CATALOG: "Catálogo",
    Icons.CATEGORY: "Categorías", Icons.CHART: "Gráfica", Icons.CHECKLIST: "Lista de verificación",
    Icons.COLD: "Enfriamiento", Icons.COMPANY: "Empresa", Icons.CONDEMN: "Decomiso",
    Icons.COST: "Costo", Icons.COUNT: "Conteo", Icons.CUT: "Corte", Icons.CUTTING: "Despiece",
    Icons.DASHBOARD: "Resumen", Icons.DERIVED: "Productos derivados", Icons.DEVICE: "Dispositivos",
    Icons.DIFFERENCE: "Diferencias", Icons.DISPATCH: "Despacho", Icons.DISPLAY: "Pantalla",
    Icons.DISPOSAL: "Disposición", Icons.DOCUMENT: "Documento", Icons.DRIVER: "Repartidor",
    Icons.EXPIRY: "Caducidad", Icons.EXTERNAL: "Catálogo externo", Icons.FAILED: "Fallido",
    Icons.FLAG: "Bandera", Icons.FORECAST: "Pronóstico", Icons.GRADE: "Clasificación",
    Icons.IMPORT: "Importación", Icons.INCIDENT: "Incidencia", Icons.INSPECTION: "Inspección",
    Icons.INTEGRATION: "Integraciones", Icons.INTERNAL: "Producto interno", Icons.INVESTIGATION: "Investigación",
    Icons.KITCHEN: "Preparación", Icons.LIST: "Lista", Icons.LOCATION: "Ubicación",
    Icons.LOT: "Lote", Icons.LOTS: "Lotes", Icons.MATERIAL: "Materiales", Icons.MEAT: "Producto cárnico",
    Icons.MOVEMENTS: "Movimientos", Icons.OFFLINE: "Sin conexión", Icons.ORDERS: "Órdenes",
    Icons.PACKAGE: "Empaque", Icons.PENDING: "Pendiente", Icons.PICKING: "Preparar mercancía",
    Icons.PICKUP: "Recoger pedido", Icons.PRICE: "Precio", Icons.PURCHASE: "Compra",
    Icons.QUALITY: "Calidad", Icons.RECEIPT: "Recepción", Icons.RECEIVING: "Recibir mercancía",
    Icons.RECIPE: "Receta", Icons.RECOMMENDATION: "Recomendación", Icons.RECOVERY: "Recuperación",
    Icons.REDO: "Reintentar", Icons.REPLENISHMENT: "Reposición", Icons.REPORT: "Reporte",
    Icons.REQUEST: "Solicitud", Icons.RESERVATION: "Reserva", Icons.RETURN: "Devolución",
    Icons.REWORK: "Reproceso", Icons.ROUTE: "Ruta", Icons.SCALE: "Báscula",
    Icons.SCENARIO: "Escenario", Icons.SCHEDULE: "Programación", Icons.SETTLEMENT: "Liquidación",
    Icons.SPECIES: "Especie", Icons.SUGGESTION: "Sugerencia", Icons.SUPPLIER: "Proveedor",
    Icons.TASKS: "Tareas", Icons.TEMPERATURE: "Temperatura", Icons.THEME: "Apariencia",
    Icons.TRACE: "Trazabilidad", Icons.TRACEABILITY: "Trazabilidad", Icons.TRACKING: "Seguimiento",
    Icons.TRANSFER: "Transferencia", Icons.TRANSIT: "En tránsito", Icons.UNIT: "Unidad de medida",
    Icons.USERS: "Usuarios", Icons.WAREHOUSE: "Almacén", Icons.WASTE: "Merma", Icons.YIELD: "Rendimiento",
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

# Interface artwork is drawn on the same 24-unit grid and stroke contract.
# Synonyms share a vector only when they communicate the same concept.
_PATHS.update({
    Icons.ACTIVITY: '<path d="M2 12h4l3-9 6 18 3-9h4"/>',
    Icons.ADJUSTMENT: '<path d="M5 2v5m0 4v11M12 2v12m0 4v4M19 2v2m0 4v14M2 7h6v4H2ZM9 14h6v4H9ZM16 4h6v4h-6Z"/>',
    Icons.AUDIT: '<path d="M12 22H4V4h4m8 0h4v6M8 2h8v4H8ZM8 10h5m-5 4h3"/><circle cx="16" cy="16" r="4"/><path d="m19 19 3 3"/>',
    Icons.BARCODE: '<path d="M2 3v18M6 3v18M9 3v18M14 3v18M18 3v18M22 3v18"/>',
    Icons.BRANCH: '<path d="M3 9v13h18V9M2 9l3-7h14l3 7ZM8 22v-8h8v8M2 9a3 3 0 0 0 5 2 3 3 0 0 0 5 0 3 3 0 0 0 5 0 3 3 0 0 0 5-2"/>',
    Icons.BUNDLE: '<path d="m12 2 5 3v6l-5 3-5-3V5ZM2 13l5-3 5 3v6l-5 3-5-3Zm10 0 5-3 5 3v6l-5 3-5-3"/>',
    Icons.CARCASS: '<path d="M10 4a2 2 0 1 1 4 0c0 2-2 2-2 4M12 8l8 5H4ZM7 13v4a5 5 0 0 0 10 0v-4M12 14v7"/>',
    Icons.CATALOG: '<path d="M12 5C8 2 5 2 2 3v17c4-1 7 0 10 2 3-2 6-3 10-2V3c-3-1-6-1-10 2Zm0 0v17M5 7l4 1M5 11l4 1m6-4 4-1m-4 5 4-1"/>',
    Icons.CATEGORY: '<rect x="2" y="2" width="8" height="8" rx="1"/><rect x="14" y="2" width="8" height="8" rx="1"/><rect x="2" y="14" width="8" height="8" rx="1"/><rect x="14" y="14" width="8" height="8" rx="1"/>',
    Icons.CHECKLIST: '<path d="M8 4H4v18h16V4h-4M8 2h8v4H8ZM7 10l1 1 2-2m3 1h4M7 16l1 1 2-2m3 1h4"/>',
    Icons.COLD: '<path d="M12 2v20M3 7l18 10M3 17 21 7M9 3l3 3 3-3M9 21l3-3 3 3M3 10l4-1-1-4m12 0-1 4 4 1M3 14l4 1-1 4m12 0-1-4 4-1"/>',
    Icons.COMPANY: '<path d="M3 22V2h12v20M15 10h6v12M7 6h1m3 0h1M7 10h1m3 0h1M7 14h1m3 0h1M7 22v-4h4v4M18 14h1m-1 4h1"/>',
    Icons.COST: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M7 5h10v4H7ZM7 13h2m-2 4h2m4-4h4m-4 4h4"/>',
    Icons.COUNT: '<path d="M4 3v18M9 3v18M14 3v18M19 3v18M2 18 22 6"/>',
    Icons.CUT: '<path d="m3 21 6-6m-3-3 3 3c5-1 10-7 13-13C14 4 8 7 6 12ZM3 16l5 5"/>',
    Icons.DASHBOARD: '<rect x="2" y="2" width="8" height="12" rx="1"/><rect x="14" y="2" width="8" height="6" rx="1"/><rect x="14" y="12" width="8" height="10" rx="1"/><rect x="2" y="18" width="8" height="4" rx="1"/>',
    Icons.DERIVED: '<path d="M8 2h8M10 2v7L3 20v2h18v-2L14 9V2M7 15h10M9 19h1m4-2h1"/>',
    Icons.DIFFERENCE: '<path d="M3 8h18M3 16h18M16 3 8 21"/>',
    Icons.DISPLAY: '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M12 17v5M7 22h10"/>',
    Icons.DRIVER: '<circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/><path d="M2 12h7m6 0h7M12 15v7"/>',
    Icons.EXTERNAL: '<path d="M10 3H3v18h18v-7M14 2h8v8M22 2 10 14"/>',
    Icons.FLAG: '<path d="M4 22V2c6-4 10 4 16 0v12c-6 4-10-4-16 0"/>',
    Icons.FORECAST: '<path d="M2 2v20h20M5 17l5-6 4 2 7-9m-6 0h6v6"/>',
    Icons.GRADE: '<circle cx="12" cy="8" r="6"/><path d="m8 13-3 9 7-3 7 3-3-9m-7-5 2 2 4-4"/>',
    Icons.IMPORT: '<path d="M12 2v14m-5-5 5 5 5-5M3 14v7h18v-7"/>',
    Icons.INTEGRATION: '<rect x="2" y="2" width="6" height="6" rx="1"/><rect x="16" y="16" width="6" height="6" rx="1"/><path d="M8 5h8a3 3 0 0 1 3 3v3m-3-3 3 3 3-3M16 19H8a3 3 0 0 1-3-3v-3m-3 3 3-3 3 3"/>',
    Icons.INTERNAL: '<path d="m12 2 10 5v10l-10 5-10-5V7Zm-10 5 10 5 10-5M12 12v10M8 5l8 4"/><path d="m15 15 2 1 2-1v4l-2 1-2-1Z"/>',
    Icons.KITCHEN: '<path d="M6 15a5 5 0 1 1 1-10 5 5 0 0 1 10 0 5 5 0 1 1 1 10v7H6ZM6 18h12M9 10v5m6-5v5"/>',
    Icons.LIST: '<path d="M8 5h14M8 12h14M8 19h14M2 5h1m-1 7h1m-1 7h1"/>',
    Icons.LOT: '<path d="M2 7h14v15H2ZM5 3h14v15M8 1h14v14M6 11h6M6 15h6M6 19h3"/>',
    Icons.MATERIAL: '<path d="m12 2 10 5-10 5L2 7ZM2 12l10 5 10-5M2 17l10 5 10-5"/>',
    Icons.MEAT: '<path d="M3 12C0 5 7 1 13 2s10 7 8 13-9 8-14 5-2-3-4-8Z"/><path d="M7 8c2-4 11-2 10 4s-7 5-10 2-2-3 0-6Z"/>',
    Icons.OFFLINE: '<path d="m2 2 20 20M2 9c2-2 4-3 6-3m5-1c4 0 7 1 9 4M5 13c2-2 4-3 7-3m5 1 2 2M9 17c2-2 4-2 6 0M12 21h0"/>',
    Icons.ORDERS: '<path d="M8 4H4v18h16V4h-4M8 2h8v4H8ZM8 10h8M8 14h8M8 18h5"/>',
    Icons.PICKING: '<path d="m12 2 10 5v6M2 7v10l10 5M2 7l10 5 10-5M12 12v10M7 4l10 5m-1 9 2 2 4-5"/>',
    Icons.PICKUP: '<path d="M3 14v8M3 20h12l7-6c-1-2-3-2-5 0l-3 2M3 14l5-2h5c3 0 3 4 0 4H8M9 2h10v7H9ZM14 2v3"/>',
    Icons.PRICE: '<path d="M2 2h10l10 10-10 10L2 12Z"/><circle cx="7" cy="7" r="1.5"/>',
    Icons.QUALITY: '<path d="M12 2 3 6v7c0 5 9 9 9 9s9-4 9-9V6ZM7 12l3 3 7-7"/>',
    Icons.RECIPE: '<path d="M4 2h16v20H4ZM8 2v20M11 7h6M11 11h6M11 15h4"/>',
    Icons.RECOMMENDATION: '<path d="M8 17c0-3-4-4-4-9a8 8 0 1 1 16 0c0 5-4 6-4 9ZM8 20h8m-6 3h4M12 17V9m-3-2 3 2 3-2"/>',
    Icons.RECOVERY: '<path d="m9 5 3-4 5 8M2 16l4-7 4 1m-4-1 1 5M9 22H3l-2-4M13 22h7l3-4-4-6m-3-7 1 4 4-1M13 18l-3 4 3 2"/>',
    Icons.REPLENISHMENT: '<path d="M2 7h13v15H2ZM2 11h13M18 3v10M13 8h10"/>',
    Icons.REPORT: '<path d="M4 2h16v20H4ZM8 17v-5m4 5V7m4 10v-7"/>',
    Icons.REQUEST: '<path d="M8 4H4v18h16V4h-4M8 2h8v4H8ZM12 10v8m-4-4h8"/>',
    Icons.RESERVATION: '<rect x="2" y="10" width="14" height="12" rx="2"/><path d="M5 10V6a4 4 0 0 1 8 0v4M9 15v3M19 6h3m-3 5h3m-3 5h3"/>',
    Icons.RETURN: '<path d="m8 2-6 6 6 6M2 8h12a8 8 0 0 1 0 16"/>',
    Icons.ROUTE: '<circle cx="5" cy="4" r="3"/><circle cx="19" cy="20" r="3"/><path d="M8 4h8a4 4 0 0 1 0 8H8a4 4 0 0 0 0 8h8"/>',
    Icons.SCALE: '<path d="M3 9h18l-2 13H5ZM8 9V6a4 4 0 0 1 8 0v3M12 6l2-2M8 13h8v5H8Z"/>',
    Icons.SCENARIO: '<path d="M12 22V12M3 2l4 4-4 4m18-8-4 4 4 4M7 6c5 0 5 6 5 6s0-6 5-6"/>',
    Icons.SETTLEMENT: '<path d="M3 2h14v20H3ZM6 6h8M6 10h4M6 14h4m-4 4h4M15 14l3 3 5-6"/>',
    Icons.SPECIES: '<path d="M7 14c-6 6 0 10 5 6 5 4 11 0 5-6-3-4-7-4-10 0Z"/><ellipse cx="4" cy="9" rx="2" ry="3"/><ellipse cx="9" cy="5" rx="2" ry="3"/><ellipse cx="15" cy="5" rx="2" ry="3"/><ellipse cx="20" cy="9" rx="2" ry="3"/>',
    Icons.TEMPERATURE: '<path d="M9 14V5a3 3 0 0 1 6 0v9a5 5 0 1 1-6 0M12 8v9m6-12h3m-3 4h3"/><circle cx="12" cy="18" r="1.5"/>',
    Icons.THEME: '<circle cx="12" cy="12" r="10"/><path d="M12 2v20M12 5l5 1m-5 3 8 1m-8 3 9 1m-9 3 7 1"/>',
    Icons.TRACEABILITY: '<rect x="8" y="2" width="8" height="6" rx="1"/><rect x="2" y="16" width="7" height="6" rx="1"/><rect x="15" y="16" width="7" height="6" rx="1"/><path d="M12 8v4M5 16v-4h14v4"/>',
    Icons.UNIT: '<path d="m2 16 14-14 6 6L8 22ZM6 12l3 3m1-7 3 3m1-7 3 3"/>',
    Icons.WASTE: '<path d="m12 2 10 5v10l-10 5-10-5V7Zm-10 5 10 5 10-5M12 12l-3 3 5 2-2 5M7 4l10 5"/>',
    Icons.YIELD: '<circle cx="7" cy="7" r="4"/><circle cx="17" cy="17" r="4"/><path d="M3 21 21 3"/>',
})
for _name, _equivalent in {
    Icons.ALERT: Icons.WARNING, Icons.ANIMAL_LOT: Icons.SPECIES,
    Icons.APPROVAL: Icons.CHECKLIST, Icons.BELL: Icons.NOTIFICATIONS,
    Icons.CHART: Icons.ANALYTICS, Icons.CONDEMN: Icons.ERROR,
    Icons.CUTTING: Icons.CUT, Icons.DEVICE: Icons.DISPLAY,
    Icons.DISPATCH: Icons.DELIVERY, Icons.DISPOSAL: Icons.DELETE,
    Icons.DOCUMENT: Icons.FILE, Icons.EXPIRY: Icons.CALENDAR,
    Icons.FAILED: Icons.ERROR, Icons.INCIDENT: Icons.WARNING,
    Icons.INSPECTION: Icons.QUALITY, Icons.INVESTIGATION: Icons.SEARCH,
    Icons.LOCATION: Icons.ADDRESS, Icons.LOTS: Icons.LOT,
    Icons.MOVEMENTS: Icons.TRANSFERS, Icons.PACKAGE: Icons.PRODUCTS,
    Icons.PENDING: Icons.CLOCK, Icons.PURCHASE: Icons.PURCHASES,
    Icons.RECEIPT: Icons.SALES, Icons.RECEIVING: Icons.IMPORT,
    Icons.REDO: Icons.REFRESH, Icons.REWORK: Icons.RECOVERY,
    Icons.SCHEDULE: Icons.CALENDAR, Icons.SUGGESTION: Icons.RECOMMENDATION,
    Icons.SUPPLIER: Icons.BRANCH, Icons.TASKS: Icons.CHECKLIST,
    Icons.TRACE: Icons.TRACEABILITY, Icons.TRACKING: Icons.ROUTE,
    Icons.TRANSFER: Icons.TRANSFERS, Icons.TRANSIT: Icons.DELIVERY,
    Icons.USERS: Icons.CUSTOMERS, Icons.WAREHOUSE: Icons.INVENTORY,
}.items():
    _PATHS[_name] = _PATHS[_equivalent]
del _name, _equivalent


class IconProvider:
    """Canonical vector icons; bind live controls, use icon() for snapshots."""

    @classmethod
    def icon(cls, name: str, *, size: int = 20, state: str = "normal", theme=None):
        from PyQt5.QtGui import QIcon

        return QIcon(cls._engine(name, size=size, state=state, theme=theme))

    @classmethod
    def pixmap(cls, name: str, *, size: int = 20, state: str = "normal", theme=None,
               device_pixel_ratio: float = 1.0, enabled: bool = True):
        """Rasterize a label/export at its actual DPR, retaining logical size."""
        from PyQt5.QtCore import QSize
        from PyQt5.QtGui import QIcon

        if device_pixel_ratio <= 0:
            raise ValueError("Icon device pixel ratio must be positive")
        engine = cls._engine(name, size=size, state=state, theme=theme)
        pixels = max(1, round(size * device_pixel_ratio))
        mode = QIcon.Normal if enabled else QIcon.Disabled
        pixmap = engine.pixmap(QSize(pixels, pixels), mode, QIcon.Off)
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        return pixmap

    @classmethod
    def _engine(cls, name, *, size, state, theme):
        import logging
        from frontend.desktop.themes.theme_manager import ThemeManager
        from frontend.desktop.themes.semantic_colors import SemanticColors

        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            raise ValueError("Icon size must be a positive integer")
        colors = SemanticColors.for_theme(theme or ThemeManager.instance().theme)
        color = {
            "normal": colors.TEXT_SECONDARY, "hover": colors.PRIMARY_DEFAULT,
            "selected": colors.PRIMARY_DEFAULT, "disabled": colors.TEXT_DISABLED,
            "danger": colors.DANGER_DEFAULT, "success": colors.SUCCESS_DEFAULT,
            "warning": colors.WARNING_DEFAULT, "info": colors.INFO_DEFAULT,
            "inverse": colors.TEXT_INVERSE,
        }.get(state, colors.TEXT_SECONDARY)
        if name not in _PATHS:
            logging.getLogger(__name__).warning("Unknown icon identifier %r; using file symbol", name)
            name = Icons.FILE
        active = color if state in ("inverse", "danger", "success", "warning", "info", "disabled") else colors.PRIMARY_DEFAULT
        return _SvgIconEngine(_PATHS[name], color, active, colors.TEXT_DISABLED)

    @classmethod
    def bind(cls, widget, name: str, *, size: int = 20, state: str = "normal"):
        """Follow theme/lifetime; preserve supplied accessibility and native states."""
        from PyQt5.QtCore import QSize
        from frontend.desktop.themes.theme_manager import ThemeManager

        previous = getattr(widget, "_spj_icon_binding", None)
        from PyQt5 import sip
        if previous is not None and not sip.isdeleted(previous):
            previous.detach()
            previous.deleteLater()
        binding = _IconBinding(widget, cls, name, size, state, ThemeManager.instance())
        widget._spj_icon_binding = binding
        widget.setProperty("icon", name)
        if hasattr(widget, "setIconSize"):
            widget.setIconSize(QSize(size, size))
        if hasattr(widget, "accessibleName"):
            current_name = widget.accessibleName()
            generated_name = getattr(previous, "_accessible_name", None)
            if not current_name or current_name == generated_name:
                binding._accessible_name = icon_accessible_name(name)
                widget.setAccessibleName(binding._accessible_name)
        binding.refresh()
        return binding


# Qt imports are kept after the catalog so its assets remain straightforward data.
from PyQt5.QtCore import QByteArray, QEvent, QObject, QRectF, QSize, Qt, pyqtSlot
from PyQt5.QtGui import QIcon, QIconEngine, QPainter, QPixmap
from PyQt5.QtSvg import QSvgRenderer


class _SvgIconEngine(QIconEngine):
    """Render the source vector at the requested size instead of scaling bitmaps."""

    def __init__(self, path, normal, active, disabled):
        super().__init__()
        self._path = path
        self._colors = normal, active, disabled
        self._renderers = {}

    def clone(self):
        return _SvgIconEngine(self._path, *self._colors)

    def key(self):
        return "spj.semantic.svg"

    def actualSize(self, size, mode, state):
        return QSize(size)

    def paint(self, painter, rect, mode, state):
        normal, active, disabled = self._colors
        color = disabled if mode == QIcon.Disabled else (
            active if mode in (QIcon.Active, QIcon.Selected) or state == QIcon.On else normal)
        renderer = self._renderers.get(color)
        if renderer is None:
            svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
                   f'fill="none" stroke="{color}" stroke-width="1.8" '
                   f'stroke-linecap="round" stroke-linejoin="round">{self._path}</svg>')
            renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
            self._renderers[color] = renderer
        side = min(rect.width(), rect.height())
        bounds = QRectF(rect.x() + (rect.width() - side) / 2,
                        rect.y() + (rect.height() - side) / 2, side, side)
        renderer.render(painter, bounds)

    def pixmap(self, size, mode, state):
        pixmap = QPixmap(size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        try:
            self.paint(painter, pixmap.rect(), mode, state)
        finally:
            painter.end()
        return pixmap


class _IconBinding(QObject):
    def __init__(self, target, provider, name, size, state, manager):
        import weakref
        super().__init__(target)
        self._target = weakref.ref(target)
        self._manager = weakref.ref(manager)
        self._window = None
        self._accessible_name = None
        self._provider, self._name, self._size, self._state = provider, name, size, state
        target.installEventFilter(self)
        manager.theme_changed.connect(self.refresh)
        self._follow_screen(target)

    def detach(self):
        from PyQt5 import sip
        manager, target = self._manager(), self._target()
        if manager is not None and not sip.isdeleted(manager):
            manager.theme_changed.disconnect(self.refresh)
        if target is not None and not sip.isdeleted(target):
            target.removeEventFilter(self)
        self._disconnect_screen()

    def _disconnect_screen(self):
        from PyQt5 import sip
        window = self._window
        if window is not None and not sip.isdeleted(window):
            window.screenChanged.disconnect(self._screen_changed)
        self._window = None

    def _follow_screen(self, target):
        if not hasattr(target, "window"):
            return
        window = target.window().windowHandle()
        if window is self._window:
            return
        self._disconnect_screen()
        if window is not None:
            self._window = window
            window.screenChanged.connect(self._screen_changed)

    @pyqtSlot()
    def _screen_changed(self):
        self.refresh()

    @pyqtSlot(str)
    def refresh(self, _theme=None):
        from PyQt5 import sip
        target, manager = self._target(), self._manager()
        if target is None or sip.isdeleted(target):
            return
        state = self._state
        if state in ("normal", "neutral") and target.property("variant") in ("primary", "danger"):
            state = "inverse"
        theme = manager.theme if manager is not None and not sip.isdeleted(manager) else None
        if hasattr(target, "setIcon"):
            target.setIcon(self._provider.icon(self._name, size=self._size, state=state, theme=theme))
        else:
            target.setPixmap(self._provider.pixmap(
                self._name, size=self._size, state=state, theme=theme,
                device_pixel_ratio=target.devicePixelRatioF(), enabled=target.isEnabled()))

    def eventFilter(self, target, event):
        # QLabel snapshots need explicit enabled/DPI refresh; button/action modes
        # remain controlled by Qt. Reparenting/showing can move a label to a monitor.
        if event.type() in (QEvent.Show, QEvent.ParentChange):
            self._follow_screen(target)
            self.refresh()
        elif event.type() == QEvent.EnabledChange:
            self.refresh()
        elif event.type() == QEvent.DynamicPropertyChange and bytes(event.propertyName()) == b"variant":
            self.refresh()
        return super().eventFilter(target, event)
