"""Helper compartido: DB SQLite en memoria born-clean (schema canónico m000)."""
from __future__ import annotations

import sqlite3


def make_db() -> sqlite3.Connection:
    import importlib

    from migrations import m000_base_schema as m000

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    m000.up(conn)
    # Migraciones canónicas que otras suites/servicios asumen presentes.
    # Se aplican en el mismo orden que migrations/engine.py.
    for module_name in (
        "migrations.standalone.057_loyalty_ledger_unificado",
        "migrations.standalone.082_treasury_tables",
        "migrations.standalone.083_financial_traceability_tables",
        "migrations.standalone.084_capital_movements",
        "migrations.standalone.092_loyalty_ledger_canonicalization",
        "migrations.standalone.098_canonical_inventory",
        "migrations.standalone.206_installation_provisioning_schema",
        "migrations.standalone.207_authentication_schema",
        "migrations.standalone.208_settings_configuration_governance_schema",
        "migrations.standalone.209_settings_company_branch_profile_schema",
        "migrations.standalone.210_settings_workstation_schema",
        "migrations.standalone.211_device_management_schema",
        "migrations.standalone.212_print_routing_schema",
        "migrations.standalone.213_scale_reader_diagnostics_schema",
        "migrations.standalone.214_document_output_schema",
        "migrations.standalone.215_marketing_campaigns_schema",
        "migrations.standalone.216_document_numbering_schema",
        "migrations.standalone.217_customer_display_schema",
        "migrations.standalone.218_content_and_advertising_schema",
        "migrations.standalone.219_integrations_schema",
        "migrations.standalone.220_notifications_schema",
        "migrations.standalone.221_feature_flags_schema",
        "migrations.standalone.222_appearance_schema",
        "migrations.standalone.223_offline_schema",
        "migrations.standalone.224_configuracion_security_schema",
    ):
        module = importlib.import_module(module_name)
        run = getattr(module, "run", None) or getattr(module, "up", None)
        if run is not None:
            run(conn)
    return conn
