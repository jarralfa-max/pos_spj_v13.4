# Lote 5 — Núcleo y configuración

- **Rama:** `fix/lote-5`, sobre `claude/erp-financial-bounded-context-uqxz6b`.
- **Migraciones:** ninguna. No se usó el rango 365–367.
- **Aprobaciones:** `e58f6849` traído con cherry-pick (`88acabf5`).

## Estado por ítem

| Ítem | Estado | Commit | Prueba que lo cubre |
|---|---|---|---|
| SDLC-SET-001 | LISTO | `b09b1514` | `tests/integration/shell/test_installation_branch_session_follow.py`, `tests/unit/bootstrap/test_application_context_service.py` |
| SDLC-CORE-012 | LISTO | `0a524a0f` | `tests/unit/test_core012_*`, `tests/integration/transfers/test_core012_*`, `tests/integration/meat_processing/test_core012_*` |
| SDLC-BI-001 | LISTO | PENDIENTE | `tests/integration/test_bi_branch_scope.py`, `tests/unit/business_intelligence/test_bi_filter_bar.py` |
| SDLC-CORE-001 | LISTO | `ebd59dde` | `tests/integration/bootstrap/test_event_wiring_isolation.py` |
| SDLC-CORE-007 | LISTO | `a53e523b` | `tests/integration/test_sqlite_sales_repository_uuid.py` + colección completa |
| SDLC-ARQ-TEST-001 | LISTO | PENDIENTE | `tests/integration/test_multi_station_harness.py`, `tests/integration/configuracion/test_installation_branch_resolution.py` |
