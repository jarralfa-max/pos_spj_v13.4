# Integración ronda 1 — reparación de los merges de los lotes 1–10

- **Rama:** `fix/integracion-ronda-1`, que sale de `claude/erp-financial-bounded-context-uqxz6b` en `6ef92643` (los PR #337–#346 ya integrados).
- **Base antes de los merges:** `ff2061a1`. Entre `ff2061a1` y los merges sólo entró `1d0ea1c6` (sólo `BACKLOG.md`).
- **Fuente de verdad:** las ramas locales `fix/lote-1` … `fix/lote-10`.
- **Fecha:** 2026-11-13.

## Cómo se midió

Los detectores 1 y 5 se corrieron sobre `6ef92643`, la integración sin reparar. Los detectores 2, 3 y 4 se corrieron sobre `6ef92643` y se repitieron sobre la punta reparada: sólo queda lo explicado abajo. El detector 6 se corrió una vez, con el código ya reparado (`7b5c6fac`). Los scripts quedan fuera del repositorio, en el scratchpad de la sesión.

1. **Hunks por lote.** Cada hunk de `git diff ff2061a1...fix/lote-N` se prueba con `git apply --check` en ambos sentidos: si el inverso aplica, el cambio está; si aplica el directo, se perdió; si no aplica ninguno, se revisa a mano. Resultado: 0 hunks perdidos sin explicación (los mixtos se listan abajo) y 0 archivos borrados por un lote que reaparezcan.
2. **Líneas agregadas por cada lote que faltan en HEAD.** Es la versión rápida de `lost_lines.py`.
3. **Líneas que un lote eliminó y que reaparecen en HEAD.** Así aparece un injerto, porque el código viejo vuelve.
4. **Trabajo de la base que se perdió.** Son líneas de `ff2061a1` que faltan en HEAD y que ningún lote eliminó. Sólo sale `BACKLOG.md`, por `1d0ea1c6`, y es esperado.
5. **Merges que tomaron un solo lado.** Para cada merge de `ff2061a1..HEAD`, se buscan los archivos cambiados por ambos padres. Si el resultado es idéntico a uno de los padres, se perdió el otro lado; si no es idéntico a ninguno, se revisa a mano.
6. **Nombres globales no definidos (estilo F821) y atributos `self.X` leídos y nunca asignados en su clase.** Se corrieron sobre los 440 `.py` de `git diff --name-only ff2061a1 HEAD`. `undef_names.py` no ve atributos, y por eso no detectó la pérdida 8.
7. **Pruebas sobre `6ef92643`**, sólo en algunos grupos: re-anclaje, pruebas del lote 2 y drenado de outbox. Cada grupo de fallas apuntó a una pérdida. Las pruebas por área completas se corrieron sólo sobre la rama reparada (abajo).

## Pérdidas encontradas y qué se restauró

| # | Archivo | Lote / ID | Cómo se detectó | Qué se restauró | Prueba que la cubre |
|---|---|---|---|---|---|
| 1 | `frontend/desktop/shell/desktop_shell_window_composition.py` | 2 / SDLC-HR-002 | Hunk perdido; `NameError` al construir los servicios de fondo | `def _hr_outbox_tick` (texto de `fix/lote-2`) | `tests/integration/finance/test_hr002_payroll_delivery.py` (2 en rojo → verde) |
| 2 | `backend/application/event_handlers/finance/procurement_immediate_payment_bridge.py` | 2 / SDLC-FIN-002 | Hunk mixto; `NameError` en toda compra de contado `ASSET` | import de `register_purchased_asset_in` | `tests/integration/finance/test_fin002_purchased_asset.py` (3 en rojo → verde) |
| 3 | `migrations/engine.py` | 1, 2, 6, 7, 8, 9 | Hunks mixtos; el merge de la base en los lotes 2, 8 y 9 tomó un solo lado | Registro de 354, 357, 358, 359, 360, 368, 374, 380, 381, 388 y 392, con la línea exacta de cada rama y en orden numérico | Nueva `tests/architecture/test_standalone_migrations_registered.py`, que falla con el `engine.py` anterior; también `test_fin002_purchased_asset.py::TestMigracion380` |
| 4 | `migrations/MIGRATION_LOG.md` | 1, 2, 4, 6, 8, 9 | Encabezados ausentes; merges que tomaron un solo lado | 270 líneas, el texto exacto de cada rama. Los lotes 1 y 2 van antes de la entrada del lote 3 y los lotes 4, 6, 8 y 9 después. No se duplican las de los lotes 3 y 7 | Verificación: cada encabezado de cada lote aparece exactamente una vez |
| 5 | `backend/bootstrap/wiring/event_wiring.py` | 6 / SDLC-ORD-001 | Hunks mixtos; el merge en `fix/lote-5` reescribió la función como ciclo (SDLC-CORE-001) | `wire_orders_delivery` como tupla del ciclo y despacho inicial de `orders_delivery_tick` con `record_failure`, en la forma nueva y no literal | `tests/integration/bootstrap/test_outbox_drain_coverage.py::test_pedidos_tiene_tarea_de_fondo_y_consumidores` (rojo → verde) |
| 6 | `frontend/desktop/modules/business_intelligence/presenters/reports_presenter.py` | 10 / SDLC-UI-005 | El merge de la base en `fix/lote-5` se quedó con el lado del lote 5 | import de `document_palette` y `BiExportService(document_colors=document_palette())` | `tests/architecture/test_web_and_documents_use_juanis_tokens.py::test_reports_presenter_injects_the_juanis_document_palette` |
| 7 | `tests/unit/test_empresa_page_installation_branch.py` | 8 / SDLC-ARQ-TERM-002 | Hunk mixto: los lotes 5 y 8 agregaron una prueba al final y sólo quedó la del 5 | `test_editing_the_company_no_longer_allows_re_anchoring`; además `_gerente_local` recibe `CONFIGURACION.estacion.reanclar` en `tests/integration/shell/test_installation_branch_session_follow.py` (nota del lote 5) | Las dos pruebas mismas |
| 8 | `backend/application/use_cases/set_installation_branch_use_case.py` + `configuracion_routes.py` | 7 / SDLC-ARQ-PERM-001 × 8 / SDLC-ARQ-TERM-002 | **Nueva, no estaba en la lista.** El análisis previo la marcó como falso positivo («conserva la autorización de TERM-002»), pero el archivo era un injerto: `__init__` de PERM-001 (`_authz`, `_service`) con el `execute` de TERM-002 (`_auth`, `_uow_factory`, `_record_rejection`). Re-anclar la estación lanzaba `AttributeError` siempre: 23 pruebas en rojo | El texto de `fix/lote-8` con dos ajustes para la guardia de PERM-001: `execute` empieza por `require()` y la composición pasa `authorization=` por palabra clave. Para un comando válido el orden observable es el de TERM-002. Las 2 pruebas unitarias de PERM-001 se adaptan al permiso `estacion.reanclar`. **Queda como pregunta.** | `tests/integration/configuracion/test_installation_branch_reanchor_use_case.py` (17 en rojo → verde), `tests/architecture/test_configuracion_use_cases_are_authorized.py`, `tests/unit/configuracion/test_configuracion_use_cases_backend_authorization.py` |
| 9 | `docs/sdlc/items/SDLC-SYNC-002/intent.md` | 8 y 9 / SDLC-SYNC-002 | **Nueva.** Detector 3: los merges de la base en `fix/lote-1` y `fix/lote-5` se quedaron con la respuesta vieja del 2026-11-05 («configuraciones/offline»). La base `ff2061a1` y los lotes 8 y 9 traen la del 2026-11-09 (`500a3822`) | «estacion, en configuraciones» | Sin prueba (documento) |

### Falsos positivos revisados (no se tocaron)
- `configuracion_routes.py`: el cableado de conflictos de SYNC-002 sí está. El lote 7 reescribió esa línea con `authorization=authorization` por palabra clave.
- `set_installation_branch_use_case.py`: el detector de líneas lo marcaba por el docstring, pero era el injerto de la fila 8.
- `MIGRATION_LOG.md` de los lotes 3 y 7: sus entradas sí llegaron.
- Atributos `ResumeSaleUseCase._authorizer`, `SqliteTerminalIdentityRepository._query*` y `NewOrderDialog._root`: vienen de la clase base.

### Por qué no lo detectaron las guardias existentes
- **Pérdidas 1, 2, 5, 6 y 8:** cada una tenía una prueba que la detecta, y todas estaban en rojo en `6ef92643`. Después de resolver los conflictos no se corrieron las pruebas de área.
- **Pérdida 3:** no existía una guardia de registro. `tests/test_migration_audit.py` sólo comprueba que los escáneres de `scripts/audit_migrations.py` encuentran archivos, no que todo archivo esté registrado. Además falla antes de llegar ahí: busca `scripts/` en la raíz del repo, y el script vive en `pos_spj_v13.4/scripts/`. Es una falla preexistente. Por eso se agrega `test_standalone_migrations_registered.py`, estricta desde 354, con un diccionario `RETIRADAS` vacío.

## Migraciones verificadas

Se corrió `migrations.engine.up` sobre bases temporales en el scratchpad, con `PRAGMA foreign_keys=ON`. Nunca sobre una base real.

| Escenario | Resultado |
|---|---|
| Base nueva | 344 migraciones. Desde 353, en orden: 353, 354, 357, 358, 359, 360, 368, 374, 380, 381, 384, 385, 388, 392. `foreign_key_check` vacío, `integrity_check` ok |
| Relleno: base que ya corrió la lista de `6ef92643` (con 384/385) y luego la lista reparada | Corren las 11 que faltaban, sin errores. `foreign_key_check` vacío, `integrity_check` ok. Una tercera corrida no ejecuta nada |

## Preguntas para el responsable

1. **Re-anclaje: PERM-001 (lote 7) contra TERM-002 (lote 8).** Los dos lotes cambiaron el mismo caso de uso de forma incompatible:
   - PERM-001: `EMPRESA_EDITAR` con `ConfiguracionActionAuthorizer`, construido con `company_profile_service`;
   - TERM-002: `ESTACION_REANCLAR` con `ConfiguracionAuthorizationPolicy` y una unidad de trabajo, con guardas y auditoría.

   No se pueden exigir los dos permisos: la sesión autorizada de TERM-002 sólo tiene `estacion.reanclar`. Para que la estación no quedara sin poder re-anclarse se aplicó TERM-002. Lo respaldan el punto 7 del encargo, la nota del lote 5 y el propio PERM-001, que dejaba TERM-002 fuera de su alcance. Confirmar:
   - que `EMPRESA_EDITAR` ya no se verifica para re-anclar;
   - que este caso de uso recibe la política y no el `ActionAuthorizer`.

   Lo cambiado está en el commit `7b5c6fac`.
2. **Pedidos con transferencia sin referencia.** `tests/integration/test_orders_delivery_driver_cash_finance.py::TestFallaDelEfectoDeCaja::test_pago_remoto_sin_efectivo_no_exige_turno` (lote 6) falla porque SDLC-PAY-002 (lote 4, `65b8cc86`) exige referencia para `TRANSFER`. No es una pérdida del merge: es una interacción entre lotes. `RecordOrderPaymentUseCase` ya acepta `reference=`. Hay que decidir si la prueba debe dar una referencia o si Pedidos debe exigirla en su pantalla. No se cambió nada.

3. **Reverso de pedidos sin el turno de quien reembolsa.** Cuatro pruebas del lote 6 fallan por la regla de SDLC-ARQ-SHIFT-001 (lote 1, `ActiveShiftResolver`): el efectivo sale del turno operable de quien reembolsa, y estas pruebas abren el turno a nombre de un cajero y reversan con otro `actor_user_id`. Son estas:
   - `test_orders_delivery_inventory_commit.py::TestReverso::test_devuelve_exactamente_lo_que_salio`
   - `test_orders_delivery_inventory_commit.py::TestReverso::test_vuelve_al_lote_del_que_salio`
   - `test_orders_delivery_sales_finance_use_cases.py::TestReverseCustomerOrderUseCase::test_reverses_order_and_sale_together`
   - `test_orders_delivery_sales_finance_use_cases.py::TestReverseCustomerOrderUseCase::test_retry_with_same_operation_id_does_not_double_refund`

   `return_use_cases.py` combina bien los dos lotes: los 5 detectores no encuentran pérdida. Es una interacción entre lotes, no una pérdida del merge. Hay que decidir si el reverso de un pedido exige el turno de quien lo hace, como en el POS, o el del cajero que cobró. No se cambió nada.

   Prueba de que en las preguntas 2 y 3 no hay injerto: en HEAD, `payment_policy.py` es idéntico a `fix/lote-4` y `active_shift_resolver.py` a `fix/lote-1`. `sales_cash_effects_client.py` es el de `fix/lote-1` con lo que agrega el lote 4, sin cambiar la regla.

## Resultados por área

Corrida sobre `1886ea2a` (punta de esta rama, con las 9 restauraciones) desde `pos_spj_v13.4/`, con `QT_QPA_PLATFORM=offscreen` y un tope de 600 s por corrida. La máquina tiene 2 CPU, así que los tiempos son mayores que los de los informes de cada lote.

| Lote / área | Rutas | Resultado | Frente al informe del lote |
|---|---|---|---|
| 1 Caja | `tests/unit/cash_register`, `tests/integration/cash_register` | ✅ 358 passed | Sin fallas |
| 2 Finanzas/RR. HH. | `tests/integration/finance`, `tests/unit/finance`, `tests/integration/hr`, `tests/unit/hr`, `test_hr_module_migration.py` | ✅ 560 passed | Sin fallas. Antes de reparar había 6 en esta área (HR-002, FIN-002, 380) y 1 en bootstrap (ORD-001) |
| 3 Instalador | `tests/integration/bootstrap`, `software_distribution`, `tests/unit/bootstrap`, `software_distribution`, `security`, `test_app_paths_resources.py`, `test_phase2_infrastructure.py` | ✅ 679 passed | El lote dio 650 passed; las 29 de más son de lotes posteriores |
| 4 Pagos | `tests/integration/sales`, `tests/finance`, `tests/migrations`, `procurement/test_immediate_payment_bridge.py`, `e2e/test_cash_sale_refund_flow.py` | ✅ 174 passed | Sin fallas |
| 5 BI | `tests/integration/business_intelligence` | 58 passed, 8 failed | **Igual** al lote (58/8 preexistentes, `test_every_bi_page_opens.py`) |
| 5 Configuración | `tests/unit/configuracion`, `test_empresa_page_installation_branch.py` | ✅ 201 passed | Incluye las 2 pruebas adaptadas y la restaurada |
| 5 Shell | `shell/test_installation_branch_session_follow.py`, `shell/test_desktop_shell_window_composition.py` | ✅ 11 passed | Antes de reparar había 5 fallas en la primera |
| 6 Pedidos | `tests/integration/orders_delivery`, `test_orders_delivery_{outbox_dispatcher,driver_cash_finance,settlement_use_cases}.py`, `logistics/test_driver_pwa_api.py`, `test_erp_chain_wiring_ratchet.py`, `test_orders_single_pipeline_ratchet.py` | 296 passed, 1 failed | **Nueva** frente al lote: pregunta 2 (PAY-002 × ORD) |
| 6 Pedidos (resto) | Resto de `tests/{unit,integration}/test_orders_delivery_*.py` | 400 passed, 4 failed | **Nuevas** frente al lote: pregunta 3 (SHIFT-001 × ORD) |
| 4 y 6 Ventas/POS | `tests/unit/test_sales_*.py`, `tests/unit/test_pos_checkout_dialogs.py` | 465 passed, 2 failed | Las 2 son preexistentes y el lote 4 ya las listaba: `test_checkout_width_is_identical_at_both_resolutions` (geometría, tipo SDLC-UI-031) y `test_reintentar_el_cobro_no_duplica_pagos` (SDLC-CORE-010) |
| 4 y 6 Ventas/POS | `tests/integration/test_sales_*.py` | 29 passed, 2 failed | Las 2 son preexistentes y los lotes 4, 6 y 7 ya las listaban: `test_sales_checkout_settles_everything.py`, `no such column: sucursal_id` (SDLC-CORE-011) |
| 7 Seguridad | `tests/integration/security`, `test_transfers_bootstrap_migration.py`, `test_configuracion_use_cases_are_authorized.py` | ✅ 197 passed | Sin fallas |
| 7 Transferencias | `tests/integration/transfers`, un archivo por corrida | ✅ 66 passed | El lote dio 62 passed. La primera corrida completa, que pasó por el corte de red, no dejó resultado |
| 8 Sync/terminales | `tests/unit/{central_pg,central_sync,offline}`, `tests/integration/{central_pg,central_sync,sync}`, `test_cash_offline_sync.py`, `test_terminal_identity.py`, `test_installation_branch_reanchor_use_case.py` | ✅ 181 passed, 5 skipped (PostgreSQL real) | Antes de reparar había 17 fallas en el re-anclaje |
| 8 Configuración | `tests/integration/configuracion` completo | ✅ 378 passed | El lote dio 313 passed en `c9151d46` |
| 9 WhatsApp | `whatsapp_service/tests` con `PYTHONPATH` al worktree y `ERP_DB_PATH` a una base temporal vacía | 843 passed, 13 failed | **Igual** al lote (13/843 preexistentes). `whatsapp_service/` en HEAD es idéntico a `fix/lote-9` |
| 10 UI | `test_theme_tokens_dark_derivation.py`, `test_web_and_documents_use_juanis_tokens.py`, `tests/ui/test_terminal_density_scope.py`, `tests/unit/business_intelligence`, `test_customer_display_window.py` | ✅ 184 passed | Sin fallas |
| Global | `python -m compileall -q .` | ✅ sin errores | — |
| Global | Nombres no definidos y atributos sin asignar en los 440 `.py` tocados | ✅ 0 nombres nuevos; en atributos, sólo falsos positivos de clase base | — |
| Global | `tests/test_migration_audit.py` | 3 failed | Preexistente: busca `scripts/` en la raíz del repo |

Una primera corrida de WhatsApp dio 3 fallas más («configuration database does not exist») porque `ERP_DB_PATH` apuntaba a un archivo inexistente. Era un error del entorno; repetida con una base vacía, da el resultado de la tabla.

## `tests/architecture` completo

Pendiente: se lanza en segundo plano después de este commit. Línea base en `docs/sdlc/baseline/2026-10-28.md`: 22 failed, 879 passed, 1 skipped, 2 xfailed.
