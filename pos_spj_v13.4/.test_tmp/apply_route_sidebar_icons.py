"""One-off edit helper: only adds explicit UI icon metadata and binds consumers."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = {
    "cash_register": (
        "CashRegisterRoute", "CAJA", "CASH",
        {"OPERACION": "CASH", "CIERRE Y CONTROL": "SETTLEMENT", "ADMINISTRACION": "SETTINGS"},
        {
            "overview": "DASHBOARD", "shifts": "CLOCK", "ledger": "MOVEMENTS",
            "blind_count": "COUNT", "x_cut": "REPORT", "z_cut": "SETTLEMENT",
            "differences": "DIFFERENCE", "handover": "DISPATCH", "deposits": "FINANCE",
            "refunds": "RETURN", "payment_methods": "PRICE", "payment_terminals": "DISPLAY",
            "drawer_events": "CASH", "hardware": "DEVICE", "notifications": "NOTIFICATIONS",
            "audit": "AUDIT", "sync": "REFRESH", "configuration": "SETTINGS",
        },
    ),
    "customers_crm": (
        "CustomerCrmRoute", "Clientes y CRM", "CUSTOMERS",
        {"Resumen": "DASHBOARD", "Clientes": "CUSTOMERS", "Prospectos": "SEARCH",
         "Oportunidades": "SALES", "Actividades": "CALENDAR", "Atención al cliente": "REQUEST",
         "Relación comercial": "PURCHASES", "Crédito": "FINANCE", "Segmentación": "CATEGORY",
         "Comunicaciones": "PHONE", "Privacidad": "LOCK", "Control": "AUDIT"},
        {
            "customers.overview": "DASHBOARD", "customers.directory": "CUSTOMERS",
            "customers.create": "ADD", "customers.profile": "USER", "customers.edit": "EDIT",
            "customers.accounts": "COMPANY", "customers.contacts": "USERS", "customers.addresses": "ADDRESS",
            "customers.tax_profiles": "DOCUMENT", "customers.duplicates": "DIFFERENCE",
            "crm.leads": "SEARCH", "crm.lead_detail": "USER", "crm.lead_qualification": "GRADE",
            "crm.lead_conversion": "TRANSFERS", "crm.leads_discarded": "CLOSE",
            "crm.pipeline": "ROUTE", "crm.opportunities": "SALES", "crm.opportunity_detail": "DOCUMENT",
            "crm.forecast": "FORECAST", "crm.lost_opportunities": "FAILED",
            "crm.calendar": "CALENDAR", "crm.tasks": "TASKS", "crm.calls": "PHONE",
            "crm.meetings": "USERS", "crm.visits": "LOCATION", "crm.activities": "EDIT", "crm.followups": "CLOCK",
            "crm.service_cases": "LIST", "crm.case_detail": "DOCUMENT", "crm.complaints": "WARNING",
            "crm.requests": "REQUEST", "crm.incidents": "INCIDENT", "crm.sla": "CLOCK", "crm.escalations": "ALERT",
            "customers.purchase_history": "PURCHASES", "customers.order_history": "ORDERS",
            "customers.quote_history": "PRICE", "customers.return_history": "RETURN", "customers.product_affinity": "PRODUCTS",
            "customers.credit_requests": "REQUEST", "customers.credit_profiles": "USER",
            "customers.credit_exposure": "CHART", "customers.accounts_receivable": "FINANCE",
            "customers.credit_history": "MOVEMENTS", "customers.credit_alerts": "ALERT",
            "customers.segments": "CATEGORY", "customers.tags": "PRICE", "customers.territories": "LOCATION",
            "customers.portfolios": "CATALOG", "customers.ownership": "USER",
            "customers.communication_preferences": "ADJUSTMENT", "customers.consents": "APPROVAL",
            "customers.whatsapp_summary": "PHONE", "customers.notification_history": "NOTIFICATIONS",
            "customers.privacy_requests": "REQUEST", "customers.retention": "CLOCK",
            "customers.anonymization": "LOCK", "customers.data_exports": "EXPORT",
            "customers.data_quality": "QUALITY", "customers.imports": "IMPORT",
            "customers.audit": "AUDIT", "customers.settings": "SETTINGS",
        },
    ),
    "fidelidad": (
        "FidelidadRoute", "Fidelidad", "LOYALTY",
        {"Resumen": "DASHBOARD", "Programas": "LOYALTY", "Miembros": "CUSTOMERS",
         "Recompensas y retos": "FLAG", "Referidos y ciclo de vida": "USERS",
         "Instrumentos comerciales": "PRICE", "Sorteos": "RECOMMENDATION", "Control": "AUDIT"},
        {
            "fidelidad.overview": "DASHBOARD", "loyalty.programs": "LOYALTY", "loyalty.member_profile": "USER",
            "loyalty.tiers": "GRADE", "loyalty.rewards": "LOYALTY", "loyalty.challenges": "FLAG",
            "loyalty.referrals": "USERS", "loyalty.birthdays": "CALENDAR", "loyalty.campaigns": "SCHEDULE",
            "instruments.coupons": "PRICE", "instruments.vouchers": "DOCUMENT",
            "sweepstakes.campaigns": "RECOMMENDATION", "sweepstakes.draws": "CHECK",
            "fidelidad.fraud": "INVESTIGATION", "fidelidad.settings": "SETTINGS",
        },
    ),
    "tarjetas_fidelidad": (
        "TarjetasFidelidadRoute", "Tarjetas Fidelidad", "LOYALTY_CARDS",
        {"Resumen": "DASHBOARD", "Tarjetas": "LOYALTY_CARDS", "Diseño": "EDIT", "Producción": "PRODUCTION"},
        {
            "tarjetas.overview": "DASHBOARD", "tarjetas.cards": "LOYALTY_CARDS", "tarjetas.digital": "DEVICE",
            "tarjetas.templates": "DOCUMENT", "tarjetas.designer": "EDIT", "tarjetas.sheets": "LAYOUT_PLACEHOLDER",
            "tarjetas.batches": "LOTS", "tarjetas.printing": "PRINT",
        },
    ),
    "assets": (
        "AssetRoute", "Activos", "ASSETS",
        {"Resumen": "DASHBOARD", "Activos": "ASSETS", "Mantenimiento": "MAINTENANCE",
         "Costos y vida útil": "COST", "Movimientos": "MOVEMENTS", "Control físico": "INVENTORY",
         "Documentación": "DOCUMENT", "Bajas": "DISPOSAL", "Control": "AUDIT"},
        {
            "assets.overview": "DASHBOARD", "assets.directory": "ASSETS", "assets.create": "ADD",
            "assets.detail": "DOCUMENT", "assets.categories": "CATEGORY", "assets.locations": "LOCATION",
            "assets.custody": "LOCK", "assets.assignments": "USER", "assets.tags": "BARCODE",
            "assets.maintenance.overview": "DASHBOARD", "assets.maintenance.plan": "CHECKLIST",
            "assets.maintenance.work_orders": "ORDERS", "assets.maintenance.calendar": "CALENDAR",
            "assets.maintenance.corrective": "MAINTENANCE", "assets.maintenance.inspections": "INSPECTION",
            "assets.maintenance.overdue": "EXPIRY", "assets.maintenance.history": "ACTIVITY",
            "assets.costs": "COST", "assets.improvements": "MAINTENANCE",
            "assets.capitalization_proposals": "REQUEST", "assets.depreciation_projection": "FORECAST",
            "assets.movements": "DISPATCH", "assets.transfers": "TRANSFERS", "assets.loans": "CLOCK",
            "assets.physical_inventory": "INVENTORY", "assets.physical_counts": "COUNT", "assets.missing": "DIFFERENCE",
            "assets.documents": "DOCUMENT", "assets.warranties": "APPROVAL", "assets.insurance": "LOCK",
            "assets.disposals": "DISPOSAL", "assets.disposal_requests": "APPROVAL", "assets.disposal_history": "ACTIVITY",
            "assets.alerts": "ALERT", "assets.audit": "AUDIT", "assets.settings": "SETTINGS",
        },
    ),
}
# Sheet layouts are a catalog of printable panels, not a generic page fallback.
CONFIG["tarjetas_fidelidad"][4]["tarjetas.sheets"] = "CATALOG"

for module, (class_name, empty_label, module_icon, groups, icons) in CONFIG.items():
    directory = ROOT / "frontend" / "desktop" / "modules" / module
    path = directory / f"{module}_routes.py"
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    calls = [node for node in ast.walk(ast.parse(source))
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == class_name]
    changes = []
    seen = set()
    seen_groups = set()
    for node in calls:
        kwargs = {keyword.arg: keyword.value for keyword in node.keywords}
        key = ast.literal_eval(node.args[0] if node.args else kwargs["route_id"])
        group = ast.literal_eval(node.args[2] if node.args else kwargs["group"])
        seen.add(key)
        seen_groups.add(group)
        # AST columns are UTF-8 byte offsets; these calls end on ASCII lines.
        line = lines[node.end_lineno - 1]
        column = len(line.encode("utf-8")[:node.end_col_offset].decode("utf-8")) - 1
        position = offsets[node.end_lineno - 1] + column
        if node.args:
            insertion = f"    icon=Icons.{icons[key]},\n    "
        else:
            insertion = f",\n        icon=Icons.{icons[key]}"
        changes.append((position, insertion))
    assert seen == set(icons), (module, seen ^ set(icons))
    assert seen_groups == set(groups), (module, seen_groups ^ set(groups))
    for position, insertion in sorted(changes, reverse=True):
        source = source[:position] + insertion + source[position:]
    source = source.replace("    capability: str\n", "    capability: str\n    icon: str\n", 1)
    source = source.replace("from dataclasses import dataclass\n", "from dataclasses import dataclass\n\nfrom frontend.desktop.components.icons import Icons\n", 1)
    mapping = "GROUP_ICONS: dict[str, str] = {\n" + "".join(
        f'    "{name}": Icons.{icon},\n' for name, icon in groups.items()) + "}\n\n\n"
    source = source.replace("@dataclass(frozen=True)", mapping + "@dataclass(frozen=True)", 1)
    ast.parse(source)
    path.write_text(source, encoding="utf-8")
    workspace_path = directory / f"{module}_workspace.py"
    workspace = workspace_path.read_text(encoding="utf-8")
    import_line = "from frontend.desktop.components.icons import Icons\n"
    if import_line not in workspace:
        workspace = workspace.replace("from frontend.desktop.components.kpi_bar import KPIBar\n", import_line + "from frontend.desktop.components.kpi_bar import KPIBar\n", 1)
    route_import = f"from frontend.desktop.modules.{module}.{module}_routes import "
    if route_import + "(\n" in workspace:
        workspace = workspace.replace(route_import + "(\n", route_import + "(\n    GROUP_ICONS,\n", 1)
    else:
        workspace = workspace.replace(route_import, route_import + "GROUP_ICONS, ", 1)
    workspace = workspace.replace(f'self._nav.add_group("{empty_label}")', f'self._nav.add_group("{empty_label}", icon=Icons.{module_icon})')
    workspace = workspace.replace("self._nav.add_group(group)", "self._nav.add_group(group, icon=GROUP_ICONS[group])")
    workspace = workspace.replace("self._nav.add_section(route.label)", "self._nav.add_section(route.label, icon=route.icon)")
    ast.parse(workspace)
    workspace_path.write_text(workspace, encoding="utf-8")
    print(module, len(seen), "routes,", len(seen_groups), "groups")
