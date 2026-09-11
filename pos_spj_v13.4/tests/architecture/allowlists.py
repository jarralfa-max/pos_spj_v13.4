"""Temporary architecture debt allowlists for SPJ FASE 1.

Each dictionary stores current violations by file. The guardrail tests allow
the existing count and fail when a file introduces additional violations or a
new file starts violating a rule. Counts may be reduced as debt is removed.
"""

# Ratchet (Remediación F): contadores APRETADOS a la realidad actual. El total
# bajó de 371 a 187 tras las extracciones de fases previas + Remediación D
# (diálogos captura-only). test_sql_in_ui_ratchet exige igualdad exacta: agregar
# SQL en UI falla, y remover SQL obliga a bajar el contador aquí (sólo decrece).
# Módulos ya en 0 (retirados): finanzas_unificadas, productos, inventario_local,
# transferencias.
SQL_IN_UI_ALLOWLIST = {
    # VACÍA. Sus entradas toleraban SQL directo en la UI en archivos de
    # `modulos/`, `interfaz/` y `core/` que la reconstrucción borró, así que
    # se retiraron: una excepción concedida a un archivo inexistente no
    # protege nada y hace creer que la deuda sigue ahí.
    #
    # Vacía significa que la regla se cumple SIN excepciones. Si algo vuelve
    # a infringirla, la guardia lo dirá: esa es la señal que se buscaba.
}

COMMIT_ROLLBACK_IN_UI_ALLOWLIST = {
    # VACÍA. Sus entradas toleraban commit/rollback en la UI en archivos de
    # `modulos/`, `interfaz/` y `core/` que la reconstrucción borró, así que
    # se retiraron: una excepción concedida a un archivo inexistente no
    # protege nada y hace creer que la deuda sigue ahí.
    #
    # Vacía significa que la regla se cumple SIN excepciones. Si algo vuelve
    # a infringirla, la guardia lo dirá: esa es la señal que se buscaba.
}

SCHEMA_CHANGES_OUTSIDE_MIGRATIONS_ALLOWLIST = {
    # DDL canónico del bounded context financiero (ejecutado solo por la
    # migración 117):
    'pos_spj_v13.4/backend/infrastructure/db/schema/finance_schema.py': 24,
    # Bounded context de Inventario (INV-3+): DDL canónico ejecutado sólo por las
    # migraciones 121 (núcleo), 122 (lotes), 123 (cadena de frío), 124 (reservas),
    # 125 (transferencias), 126 (conteos), 127 (ajustes), 128 (cuarentena),
    # 129 (mermas), 130 (trazabilidad/genealogía), 131 (reposición: reglas +
    # sugerencias), 132 (offline-first: dispatch + cursor de sync) y 133
    # (notificaciones: rule + log).
    'pos_spj_v13.4/backend/infrastructure/db/schema/inventory_schema.py': 32,
    # Plan B: uuid_cutover es la herramienta excepcional de conservación de
    # datos (reescribe tablas por diseño); el migrador delivery añadió
    # delivery_outbox_events; born_clean_audit menciona CREATE TABLE en docstring.
    'pos_spj_v13.4/backend/infrastructure/db/uuid_cutover.py': 2,
    'pos_spj_v13.4/tools/born_clean_audit.py': 1,
    # PUR-13: modulos/compras_pro.py eliminado (era 9) — Compras es enterprise.
    'pos_spj_v13.4/scripts/seed_demo.py': 1,
    'pos_spj_v13.4/scripts/stress_test_concurrency.py': 1,
    'pos_spj_v13.4/security/rbac.py': 4,
    'pos_spj_v13.4/tests/conftest.py': 22,
    'pos_spj_v13.4/tests/test_analytics_profitability_fallback.py': 3,
    'pos_spj_v13.4/tests/test_bloque1_p0_fixes.py': 8,
    'pos_spj_v13.4/tests/test_bloque2_query_service.py': 6,
    'pos_spj_v13.4/tests/test_bloque3_motor_unificado.py': 9,
    'pos_spj_v13.4/tests/test_bootstrap_wiring.py': 6,
    'pos_spj_v13.4/tests/test_cliente_repository_schema_compat.py': 2,
    'pos_spj_v13.4/tests/test_core_services.py': 15,
    'pos_spj_v13.4/tests/test_credit_flow_refactor.py': 3,
    'pos_spj_v13.4/tests/test_credit_sale_backend_validation.py': 8,
    'pos_spj_v13.4/tests/test_credit_sale_cxc.py': 3,
    'pos_spj_v13.4/tests/test_db_connection_transaction.py': 1,
    'pos_spj_v13.4/tests/test_delivery_application_use_cases.py': 2,
    'pos_spj_v13.4/tests/test_delivery_history_audit.py': 1,
    'pos_spj_v13.4/tests/test_delivery_inventory_projection.py': 4,
    'pos_spj_v13.4/tests/test_delivery_lifecycle.py': 5,
    'pos_spj_v13.4/tests/test_delivery_outbox.py': 1,
    'pos_spj_v13.4/tests/test_delivery_phase12_required.py': 6,
    'pos_spj_v13.4/tests/test_delivery_repository_list_orders.py': 1,
    'pos_spj_v13.4/tests/test_delivery_sale_projection.py': 2,
    'pos_spj_v13.4/tests/test_delivery_schema_migrator.py': 3,
    'pos_spj_v13.4/tests/test_delivery_service.py': 1,
    'pos_spj_v13.4/tests/test_delivery_ticket_uses_escpos.py': 3,
    'pos_spj_v13.4/tests/test_delivery_ui_phase13.py': 1,
    'pos_spj_v13.4/tests/test_delivery_weight.py': 6,
    'pos_spj_v13.4/tests/test_delivery_whatsapp_notifier.py': 1,
    'pos_spj_v13.4/tests/test_driver_service.py': 3,
    'pos_spj_v13.4/tests/test_fase0_hardware_guards.py': 2,
    'pos_spj_v13.4/tests/test_fase0_produccion_historial_compat.py': 3,
    'pos_spj_v13.4/tests/test_fase0_recetas_integrity.py': 4,
    'pos_spj_v13.4/tests/test_fase0_theme_engine_persistence.py': 1,
    'pos_spj_v13.4/tests/test_fase0_theme_normalization.py': 1,
    'pos_spj_v13.4/tests/test_fase1_finance_schema_compat.py': 11,
    'pos_spj_v13.4/tests/test_fase1_printer_styles.py': 3,
    'pos_spj_v13.4/tests/test_fase2_loyalty_scanner.py': 3,
    'pos_spj_v13.4/tests/test_fase2_scan_audit.py': 1,
    'pos_spj_v13.4/tests/test_fase3_capital_account.py': 1,
    'pos_spj_v13.4/tests/test_fase3_depreciacion.py': 3,
    'pos_spj_v13.4/tests/test_fase4_decision_engine.py': 6,
    'pos_spj_v13.4/tests/test_fase5_forecast.py': 5,
    'pos_spj_v13.4/tests/test_fase5_inventory_availability_service.py': 1,
    'pos_spj_v13.4/tests/test_fase5_stock_reservations.py': 1,
    'pos_spj_v13.4/tests/test_fase6_ai_cfdi.py': 5,
    'pos_spj_v13.4/tests/test_fase6_franchise.py': 7,
    'pos_spj_v13.4/tests/test_fase6_mercadopago_cleanup.py': 1,
    'pos_spj_v13.4/tests/test_fase_g_api_gateway.py': 10,
    'pos_spj_v13.4/tests/test_fase_g_concurrency.py': 7,
    'pos_spj_v13.4/tests/test_fase_g_inventory_integrity.py': 7,
    'pos_spj_v13.4/tests/test_finance_remaining_fixes.py': 12,
    'pos_spj_v13.4/tests/test_finance_service_methods.py': 13,
    'pos_spj_v13.4/tests/test_finance_sub_services.py': 8,
    'pos_spj_v13.4/tests/test_financial_core_enforcement.py': 7,
    'pos_spj_v13.4/tests/test_financial_core_phase3.py': 2,
    'pos_spj_v13.4/tests/test_infrastructure_persistence.py': 6,
    'pos_spj_v13.4/tests/test_loyalty_application_service.py': 2,
    'pos_spj_v13.4/tests/test_loyalty_bugfix_regression.py': 4,
    'pos_spj_v13.4/tests/test_loyalty_canonical_migration.py': 13,
    'pos_spj_v13.4/tests/test_loyalty_redemption_source.py': 3,
    'pos_spj_v13.4/tests/test_loyalty_redemption_transactional.py': 2,
    'pos_spj_v13.4/tests/test_loyalty_refactor_regression.py': 9,
    'pos_spj_v13.4/tests/test_loyalty_repository_phase2.py': 5,
    'pos_spj_v13.4/tests/test_loyalty_single_accrual.py': 3,
    'pos_spj_v13.4/tests/test_mercado_pago_webhook_confirmation.py': 1,
    'pos_spj_v13.4/tests/test_new_services.py': 20,
    'pos_spj_v13.4/tests/test_notification_policy.py': 4,
    'pos_spj_v13.4/tests/test_order_badge_service.py': 8,
    'pos_spj_v13.4/tests/test_order_totals_phase8.py': 3,
    'pos_spj_v13.4/tests/test_phase0_hardening_regression.py': 5,
    'pos_spj_v13.4/tests/test_phase3_query_services.py': 4,
    'pos_spj_v13.4/tests/test_phase6_sale_loyalty_policy.py': 2,
    'pos_spj_v13.4/tests/test_production_cost_service.py': 6,
    'pos_spj_v13.4/tests/test_production_query_service.py': 14,
    'pos_spj_v13.4/tests/test_raffle_financial_safety.py': 1,
    'pos_spj_v13.4/tests/test_raffle_rules_engine.py': 1,
    'pos_spj_v13.4/tests/test_receta_repository_phase3.py': 4,
    'pos_spj_v13.4/tests/test_recipe_components_quantities_phase4.py': 8,
    'pos_spj_v13.4/tests/test_recipe_engine_costing_phase6.py': 8,
    'pos_spj_v13.4/tests/test_recipe_engine_tipo_receta_normalization.py': 7,
    'pos_spj_v13.4/tests/test_recipe_resolver.py': 4,
    'pos_spj_v13.4/tests/test_recipe_service.py': 4,
    'pos_spj_v13.4/tests/test_refactor_v133.py': 5,
    'pos_spj_v13.4/tests/test_rrhh_phase8_cleanup.py': 5,
    'pos_spj_v13.4/tests/test_sale_fulfillment_phase5.py': 4,
    'pos_spj_v13.4/tests/test_sales_customer_loyalty.py': 16,
    'pos_spj_v13.4/tests/test_sales_no_duplication.py': 7,
    'pos_spj_v13.4/tests/test_sales_no_duplication_real.py': 10,
    'pos_spj_v13.4/tests/test_sales_stock_validation_regression.py': 8,
    'pos_spj_v13.4/tests/test_sync_service_cursor_compat.py': 3,
    'pos_spj_v13.4/tests/test_ticket_branding_from_system_config.py': 1,
    'pos_spj_v13.4/tests/test_ticket_layout_repository_regression.py': 1,
    'pos_spj_v13.4/tests/test_ticket_rendering_regression.py': 7,
    'pos_spj_v13.4/tests/test_traceability_phase9.py': 12,
    'pos_spj_v13.4/tests/test_uc_inventario.py': 2,
    'pos_spj_v13.4/tests/test_ventas_fixes.py': 3,
    'pos_spj_v13.4/tests/test_wa_bridge.py': 10,
    'pos_spj_v13.4/tests/test_wa_parser.py': 2,
    'pos_spj_v13.4/tests/test_wa_refactor.py': 3,
    'pos_spj_v13.4/tests/test_wa_repositories.py': 5,
}

HARDCODED_NUMERIC_DEFAULTS_IN_UI_ALLOWLIST = {
    # VACÍA. Sus entradas toleraban valores numéricos de negocio fijos en la UI en archivos de
    # `modulos/`, `interfaz/` y `core/` que la reconstrucción borró, así que
    # se retiraron: una excepción concedida a un archivo inexistente no
    # protege nada y hace creer que la deuda sigue ahí.
    #
    # Vacía significa que la regla se cumple SIN excepciones. Si algo vuelve
    # a infringirla, la guardia lo dirá: esa es la señal que se buscaba.
}

PLAIN_PHONE_INPUTS_ALLOWLIST = {
    # VACÍA. Sus entradas toleraban QLineEdit pelado para teléfonos en archivos de
    # `modulos/`, `interfaz/` y `core/` que la reconstrucción borró, así que
    # se retiraron: una excepción concedida a un archivo inexistente no
    # protege nada y hace creer que la deuda sigue ahí.
    #
    # Vacía significa que la regla se cumple SIN excepciones. Si algo vuelve
    # a infringirla, la guardia lo dirá: esa es la señal que se buscaba.
}

ENTITY_COMBO_MASS_LOADING_ALLOWLIST = {
    # VACÍA. Sus entradas toleraban carga masiva de entidades en un QComboBox en archivos de
    # `modulos/`, `interfaz/` y `core/` que la reconstrucción borró, así que
    # se retiraron: una excepción concedida a un archivo inexistente no
    # protege nada y hace creer que la deuda sigue ahí.
    #
    # Vacía significa que la regla se cumple SIN excepciones. Si algo vuelve
    # a infringirla, la guardia lo dirá: esa es la señal que se buscaba.
}

HARDCODED_RELATIVE_PATHS_ALLOWLIST = {
    'pos_spj_v13.4/tests/test_fase0_finanzas_syntax.py': 3,
    'pos_spj_v13.4/tests/test_fase0_menu_lateral.py': 3,
    'pos_spj_v13.4/tests/test_fase1_plan_mejora.py': 1,
    'pos_spj_v13.4/tests/test_fase1_uiux_module_guards.py': 5,
    'pos_spj_v13.4/tests/test_fase5_inventory_availability_service.py': 1,
    'pos_spj_v13.4/tests/test_loyalty_event_wiring_phase7.py': 3,
    'pos_spj_v13.4/tests/test_ticket_pipeline_integration.py': 3,
}

APPCONTAINER_PASSED_TO_SERVICES_ALLOWLIST = {
    'pos_spj_v13.4/tests/test_production_application_service.py': 1,
}

DEPRECATED_SERVICES_WITH_BUSINESS_LOGIC_ALLOWLIST = {
    # VACÍA. Sus entradas toleraban lógica de negocio en servicios obsoletos en archivos de
    # `modulos/`, `interfaz/` y `core/` que la reconstrucción borró, así que
    # se retiraron: una excepción concedida a un archivo inexistente no
    # protege nada y hace creer que la deuda sigue ahí.
    #
    # Vacía significa que la regla se cumple SIN excepciones. Si algo vuelve
    # a infringirla, la guardia lo dirá: esa es la señal que se buscaba.
}

# Remediación D — Diálogos que aún ejecutan lógica de persistencia/publicación.
# Contrato objetivo: un QDialog SOLO captura → DTO/Command; el módulo delega en
# un servicio. Cada entrada es "path::Clase" con las llamadas prohibidas que aún
# contiene. Este allowlist es un RATCHET: no se admiten entradas nuevas y, cuando
# un diálogo se limpia, su entrada DEBE retirarse (el test falla si queda obsoleta).
# Referencia: DEEP_AUDIT_ALL_MODULES §8 y §17 (Remediación D), test T8.
DIALOG_BUSINESS_LOGIC_ALLOWLIST = {
    # Vacío: ningún QDialog en modulos/, ui/ o interfaz/ ejecuta SQL/commit/
    # publish/asiento. El contrato queda enforced sin deuda tolerada.
}

# CRM-1 — Allowlist de excepciones LOCALES al bounded context nuevo
# (backend/domain|application/{customers,crm,customer_service,customer_credit,
# customer_privacy}/, backend/infrastructure/db/repositories/{...}/,
# frontend/desktop/modules/customers_crm/). A diferencia de los diccionarios
# anteriores (deuda heredada de legacy que se tolera hasta que baja), este
# allowlist es sobre código NUEVO: debe permanecer vacío siempre. Si algún
# archivo bajo esas rutas necesita una excepción a un guardrail
# (test_customers_crm_*), la excepción se agrega aquí con justificación y
# CRM-1's test_customers_crm_legacy_allowlist_is_empty.py debe seguir en verde
# sólo si el propio equipo decide tolerarla explícitamente — hoy son 0.
CUSTOMERS_CRM_MODULE_ALLOWLIST: dict[str, int] = {}

# CRM-1 — Lista de consumidores LEGACY de lógica de "cliente" fuera del
# bounded context canónico nuevo (ver docs/architecture/CRM_0_CUSTOMER_MASTER_AUDIT.md
# y tests/architecture/customers_crm_guardrails.py::LEGACY_CUSTOMER_FILES).
# Esto NO es una excepción a los guardrails de customers_crm — es el registro
# de qué archivos legacy siguen siendo la ruta de producción real hasta que
# CRM-21/CRM-22 migren sus consumidores y los retiren. Cada entrada debe
# desaparecer de aquí (no solo bajar de número) cuando el archivo se elimina.
# ASSET-1 — Allowlist de excepciones LOCALES al bounded context nuevo de
# Activos/EAM (backend/domain/assets/, backend/application/assets/,
# backend/infrastructure/db/repositories/assets/, frontend/desktop/modules/assets/).
# A diferencia de los diccionarios anteriores (deuda heredada de legacy que se
# tolera hasta que baja), este allowlist es sobre código NUEVO: debe
# permanecer vacío siempre. Ver tests/architecture/test_assets_legacy_allowlist_is_empty.py.
ASSETS_MODULE_ALLOWLIST: dict[str, int] = {}

CUSTOMERS_CRM_LEGACY_CONSUMERS = {
    # modulos/clientes.py, its four modulos/dialogs/cliente_*_dialog.py
    # split files (CRM-22), and core/services/cliente_query_service.py
    # (their only consumer) were all retired — see
    # docs/refactor/CRM-24_retiro_modulo_legacy.md. Card/loyalty (tarjetas)
    # and RFM segmentation had no replacement built (Fidelidad/BI's job,
    # not Customer Master's — see that doc's "Pendiente"). CRM-34 retired
    # core/services/cliente_service.py — zero production callers (its only
    # caller, the legacy DialogoCliente form, was already retired in
    # CRM-24; its one real capability, get_crm_loyalty_summary, is
    # redundant with LoyaltyCustomerSummaryQuery already wired into
    # Customer 360) — see docs/refactor/CRM-34_legacy_purge.md.
    'pos_spj_v13.4/core/use_cases/cliente.py':
        'GestionarClienteUC (español). Fusionar con CreateCustomerUseCase '
        '(backend/application/use_cases/create_customer_use_case.py) en CRM-3.',
    'pos_spj_v13.4/repositories/cliente_repository.py':
        'Único repositorio real hoy. Base para CustomerRepository en '
        'backend/infrastructure/db/repositories/customers/ (CRM-3).',
    'pos_spj_v13.4/api/routers/clientes.py':
        'SQL directo, ruta paralela sin UC. Reescribir sobre UseCases/'
        'QueryServices canónicos (CRM-3/CRM-13).',
    'pos_spj_v13.4/application/services/customer_credit_service.py':
        'Validación de crédito en checkout, fuera de core/ y backend/. '
        'Migrar a backend/application/customer_credit (CRM-8).',
    'pos_spj_v13.4/backend/application/use_cases/create_customer_use_case.py':
        'UC nuevo (inglés) sin repositorio propio, SQL fallback propio. '
        'Mover a backend/application/customers/use_cases (CRM-3).',
    'pos_spj_v13.4/backend/application/commands/customer_commands.py':
        'UpdateCustomerCommand aislado. Mover a backend/application/customers/'
        'commands (CRM-3).',
    'pos_spj_v13.4/backend/application/queries/customer_history_query_service.py':
        'Único QueryService "en inglés" ya en producción (usado por '
        'DialogoHistorialCliente). Mover a backend/application/customers/'
        'queries sin romper el consumidor (CRM-3).',
}
