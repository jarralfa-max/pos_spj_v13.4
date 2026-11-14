# Integración ronda 1 — reparación de los merges de los lotes 1–10

- **Rama:** `fix/integracion-ronda-1`, que sale de `claude/erp-financial-bounded-context-uqxz6b` en `6ef92643` (los PR #337–#346 ya integrados).
- **Base antes de los merges:** `ff2061a1`. Entre `ff2061a1` y los merges sólo entró `1d0ea1c6` (sólo `BACKLOG.md`).
- **Fuente de verdad:** las ramas locales `fix/lote-1` … `fix/lote-10`.
- **Fecha:** 2026-11-13.

## Cómo se midió

Cada detector se corrió sobre `6ef92643` (integración sin reparar) y se repitió sobre la punta de esta rama. Los scripts quedan fuera del repositorio, en el scratchpad de la sesión.

1. **Hunks por lote.** Cada hunk de `git diff ff2061a1...fix/lote-N` se prueba con `git apply --check` en ambos sentidos: si el inverso aplica, el cambio está; si aplica el directo, se perdió; si no aplica ninguno, se revisa a mano. Resultado: 0 hunks perdidos sin explicación (los mixtos se listan abajo) y 0 archivos borrados por un lote que reaparezcan.
2. **Líneas agregadas por cada lote que faltan en HEAD.** Es la versión rápida de `lost_lines.py`.
3. **Líneas que un lote eliminó y que reaparecen en HEAD.** Así aparece un injerto, porque el código viejo vuelve.
4. **Trabajo de la base que se perdió.** Son líneas de `ff2061a1` que faltan en HEAD y que ningún lote eliminó. Sólo sale `BACKLOG.md`, por `1d0ea1c6`, y es esperado.
5. **Merges que tomaron un solo lado.** Para cada merge de `ff2061a1..HEAD`, se buscan los archivos cambiados por ambos padres. Si el resultado es idéntico a uno de los padres, se perdió el otro lado; si no es idéntico a ninguno, se revisa a mano.
6. **Nombres globales no definidos (estilo F821) y atributos `self.X` leídos y nunca asignados en su clase.** Se corrieron sobre los 440 `.py` de `git diff --name-only ff2061a1 HEAD`. `undef_names.py` no ve atributos, y por eso no detectó la pérdida 8.
7. **Pruebas por área de cada lote** sobre `6ef92643`. Cada grupo de fallas apuntó a una pérdida.

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

## Resultados por área

Pendiente: se completa al terminar la corrida.
