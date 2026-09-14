"""One-time presentation metadata edit; not part of application runtime."""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {
    "cash_register": {
        "route_class": "CashRegisterRoute", "constant": "CASH_REGISTER_ROUTES",
        "module_label": "CAJA", "module_icon": "CASH",
        "groups": {"OPERACION": "CASH", "CIERRE Y CONTROL": "SETTLEMENT", "ADMINISTRACION": "SETTINGS"},
        "routes": {
            "overview": "DASHBOARD", "shifts": "CLOCK", "ledger": "MOVEMENTS",
            "blind_count": "COUNT", "x_cut": "REPORT", "z_cut": "SETTLEMENT",
            "differences": "DIFFERENCE", "handover": "TRANSFERS", "deposits": "FINANCE",
            "refunds": "RETURN", "payment_methods": "PRICE", "payment_terminals": "DISPLAY",
            "drawer_events": "CASH", "hardware": "DEVICE", "notifications": "NOTIFICATIONS",
            "audit": "AUDIT", "sync": "REFRESH", "configuration": "SETTINGS",
        },
    },
    "customers_crm": {
        "route_class": "CustomerCrmRoute", "constant": "CUSTOMER_CRM_ROUTES",
        "module_label": "Clientes y CRM", "module_icon": "CUSTOMERS",
        "groups": {
            "Resumen": "DASHBOARD", "Clientes": "CUSTOMERS", "Prospectos": "SEARCH",
            "Oportunidades": "SCENARIO", "Actividades": "CALENDAR", "Atención al cliente": "PHONE",
            "Relación comercial": "SALES", "Crédito": "FINANCE", "Segmentación": "CATEGORY",
            "Comunicaciones": "NOTIFICATIONS", "Privacidad": "LOCK", "Control": "AUDIT",
        },
        "routes": {
            "customers.overview": "DASHBOARD", "customers.directory": "CUSTOMERS",
            "customers.create": "ADD", "customers.profile": "DOCUMENT", "customers.edit": "EDIT",
            "customers.accounts": "COMPANY", "customers.contacts": "PHONE", "customers.addresses": "ADDRESS",
            "customers.tax_profiles": "FINANCE", "customers.duplicates": "BUNDLE",
            "crm.leads": "LIST", "crm.lead_detail": "USER", "crm.lead_qualification": "GRADE",
            "crm.lead_conversion": "SCENARIO", "crm.leads_discarded": "DISPOSAL",
            "crm.pipeline": "ROUTE", "crm.opportunities": "SALES", "crm.opportunity_detail": "DOCUMENT",
            "crm.forecast": "FORECAST", "crm.lost_opportunities": "FAILED",
            "crm.calendar": "CALENDAR", "crm.tasks": "TASKS", "crm.calls": "PHONE",
            "crm.meetings": "COMPANY", "crm.visits": "LOCATION", "crm.activities": "EDIT",
            "crm.followups": "TRACKING", "crm.service_cases": "LIST", "crm.case_detail": "DOCUMENT",
            "crm.complaints": "WARNING", "crm.requests": "REQUEST", "crm.incidents": "INCIDENT",
            "crm.sla": "CLOCK", "crm.escalations": "FLAG",
            "customers.purchase_history": "PURCHASES", "customers.order_history": "ORDERS",
            "customers.quote_history": "PRICE", "customers.return_history": "RETURN",
            "customers.product_affinity": "PRODUCTS", "customers.credit_requests": "REQUEST",
            "customers.credit_profiles": "DOCUMENT", "customers.credit_exposure": "CHART",
            "customers.accounts_receivable": "FINANCE", "customers.credit_history": "MOVEMENTS",
            "customers.credit_alerts": "ALERT", "customers.segments": "CATEGORY", "customers.tags": "PRICE",
            "customers.territories": "LOCATION", "customers.portfolios": "CATALOG", "customers.ownership": "USER",
            "customers.communication_preferences": "SETTINGS", "customers.consents": "APPROVAL",
            "customers.whatsapp_summary": "PHONE", "customers.notification_history": "NOTIFICATIONS",
            "customers.privacy_requests": "REQUEST", "customers.retention": "CLOCK",
            "customers.anonymization": "LOCK", "customers.data_exports": "EXPORT",
            "customers.data_quality": "QUALITY", "customers.imports": "IMPORT",
            "customers.audit": "AUDIT", "customers.settings": "SETTINGS",
        },
    },
    "fidelidad": {
        "route_class": "FidelidadRoute", "constant": "FIDELIDAD_ROUTES",
        "module_label": "Fidelidad", "module_icon": "LOYALTY",
        "groups": {
            "Resumen": "DASHBOARD", "Programas": "LOYALTY", "Miembros": "CUSTOMERS",
            "Recompensas y retos": "GRADE", "Referidos y ciclo de vida": "SCENARIO",
            "Instrumentos comerciales": "PRICE", "Sorteos": "FLAG", "Control": "AUDIT",
        },
        "routes": {
            "fidelidad.overview": "DASHBOARD", "loyalty.programs": "LOYALTY",
            "loyalty.member_profile": "USER", "loyalty.tiers": "GRADE", "loyalty.rewards": "PACKAGE",
            "loyalty.challenges": "FLAG", "loyalty.referrals": "SCENARIO", "loyalty.birthdays": "CALENDAR",
            "loyalty.campaigns": "RECOVERY", "instruments.coupons": "PRICE", "instruments.vouchers": "DOCUMENT",
            "sweepstakes.campaigns": "SCHEDULE", "sweepstakes.draws": "SUCCESS",
            "fidelidad.fraud": "INVESTIGATION", "fidelidad.settings": "SETTINGS",
        },
    },
    "tarjetas_fidelidad": {
        "route_class": "TarjetasFidelidadRoute", "constant": "TARJETAS_FIDELIDAD_ROUTES",
        "module_label": "Tarjetas Fidelidad", "module_icon": "LOYALTY_CARDS",
        "groups": {"Resumen": "DASHBOARD", "Tarjetas": "LOYALTY_CARDS", "Diseño": "EDIT", "Producción": "PRODUCTION"},
        "routes": {
            "tarjetas.overview": "DASHBOARD", "tarjetas.cards": "LOYALTY_CARDS", "tarjetas.digital": "DEVICE",
            "tarjetas.templates": "DOCUMENT", "tarjetas.designer": "EDIT", "tarjetas.sheets": "LIST",
            "tarjetas.batches": "LOTS", "tarjetas.printing": "PRINT",
        },
    },
    "assets": {
        "route_class": "AssetRoute", "constant": "ASSET_ROUTES",
        "module_label": "Activos", "module_icon": "ASSETS",
        "groups": {
            "Resumen": "DASHBOARD", "Activos": "ASSETS", "Mantenimiento": "MAINTENANCE",
            "Costos y vida útil": "COST", "Movimientos": "MOVEMENTS", "Control físico": "INVENTORY",
            "Documentación": "DOCUMENT", "Bajas": "DISPOSAL", "Control": "AUDIT",
        },
        "routes": {
            "assets.overview": "DASHBOARD", "assets.directory": "ASSETS", "assets.create": "ADD",
            "assets.detail": "DOCUMENT", "assets.categories": "CATEGORY", "assets.locations": "LOCATION",
            "assets.custody": "LOCK", "assets.assignments": "USER", "assets.tags": "BARCODE",
            "assets.maintenance.overview": "DASHBOARD", "assets.maintenance.plan": "CHECKLIST",
            "assets.maintenance.work_orders": "ORDERS", "assets.maintenance.calendar": "CALENDAR",
            "assets.maintenance.corrective": "MAINTENANCE", "assets.maintenance.inspections": "INSPECTION",
            "assets.maintenance.overdue": "EXPIRY", "assets.maintenance.history": "CLOCK",
            "assets.costs": "COST", "assets.improvements": "RECOMMENDATION",
            "assets.capitalization_proposals": "FINANCE", "assets.depreciation_projection": "FORECAST",
            "assets.movements": "MOVEMENTS", "assets.transfers": "TRANSFERS", "assets.loans": "RETURN",
            "assets.physical_inventory": "INVENTORY", "assets.physical_counts": "COUNT", "assets.missing": "DIFFERENCE",
            "assets.documents": "DOCUMENT", "assets.warranties": "QUALITY", "assets.insurance": "LOCK",
            "assets.disposals": "REQUEST", "assets.disposal_requests": "APPROVAL", "assets.disposal_history": "CLOCK",
            "assets.alerts": "ALERT", "assets.audit": "AUDIT", "assets.settings": "SETTINGS",
        },
    },
}

for module, config in CONFIGS.items():
    path = ROOT / "frontend" / "desktop" / "modules" / module / f"{module}_routes.py"
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == config["route_class"]]
    route_ids = {node.args[0].value if node.args else next(
        kw.value.value for kw in node.keywords if kw.arg == "route_id") for node in calls}
    assert route_ids == config["routes"].keys(), (module, route_ids ^ config["routes"].keys())
    assert "    icon: str\n" not in source
    if module == "cash_register":
        lines = source.splitlines(keepends=True)
        for node in sorted(calls, key=lambda node: node.end_lineno, reverse=True):
            route_id = node.args[0].value
            lines.insert(node.end_lineno - 1, f'        icon=Icons.{config["routes"][route_id]},\n')
        source = "".join(lines)
    else:
        def add_icon(match):
            return f'{match.group(0)} icon=Icons.{config["routes"][match.group(1)]},'
        source = re.sub(r'route_id="([^"]+)",', add_icon, source)
    source = source.replace("from dataclasses import dataclass\n", "from dataclasses import dataclass\n\nfrom frontend.desktop.components.icons import Icons\n", 1)
    source = source.replace("    capability: str\n", "    capability: str\n    icon: str\n", 1)
    group_source = "GROUP_ICONS: dict[str, str] = {\n" + "".join(
        f'    "{group}": Icons.{icon},\n' for group, icon in config["groups"].items()) + "}\n\n\n"
    source = source.replace(config["constant"] + ":", group_source + config["constant"] + ":", 1)
    ast.parse(source)
    path.write_text(source, encoding="utf-8", newline="\n")

    workspace_path = path.with_name(f"{module}_workspace.py")
    workspace = workspace_path.read_text(encoding="utf-8")
    if "from frontend.desktop.components.icons import Icons" not in workspace:
        workspace = workspace.replace("from frontend.desktop.components.kpi_bar import KPIBar", "from frontend.desktop.components.icons import Icons\nfrom frontend.desktop.components.kpi_bar import KPIBar", 1)
    routes_import = f"from frontend.desktop.modules.{module}.{module}_routes import "
    if routes_import + "(" in workspace:
        workspace = workspace.replace(routes_import + "(\n", routes_import + "(\n    GROUP_ICONS,\n", 1)
    else:
        workspace = workspace.replace(routes_import + "grouped_routes", routes_import + "GROUP_ICONS, grouped_routes", 1)
    workspace = workspace.replace('self._nav.add_group("' + config["module_label"] + '")',
                                  'self._nav.add_group("' + config["module_label"] + '", icon=Icons.' + config["module_icon"] + ')')
    workspace = workspace.replace("self._nav.add_group(group)", "self._nav.add_group(group, icon=GROUP_ICONS[group])")
    workspace = workspace.replace("self._nav.add_section(route.label)", "self._nav.add_section(route.label, icon=route.icon)")
    ast.parse(workspace)
    workspace_path.write_text(workspace, encoding="utf-8", newline="\n")
    print(f"{module}: {len(route_ids)} routes, {len(config['groups'])} groups")
