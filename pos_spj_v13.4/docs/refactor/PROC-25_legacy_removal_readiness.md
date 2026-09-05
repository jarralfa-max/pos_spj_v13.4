# PROC-25 — Eliminación de legacy: Procesamiento Cárnico

Estado: **DONE dentro de su alcance real** — reauditoría confirma que
**ninguna eliminación de código es segura todavía**. Cero archivos legacy
reclasificados a `DELETE`. Este documento existe para dejar constancia
explícita de por qué, con evidencia verificable, y del checklist de
paridad que sí desbloquearía la eliminación real en una fase futura.

## Por qué esta fase no borra nada

El propio `PROC-0_legacy_audit.md` fijó la condición de cada clasificación
`BLOCKED`/`WRAP_TEMPORARILY`: no eliminar hasta tener **paridad funcional**
con la UI/Use Cases nuevos. PROC-23 (UI/UX) construyó exactamente **1 de
19** secciones de `MEAT_PROCESSING_NAV` como página funcional real
(Órdenes) — las 18 restantes (Preparación, En proceso, Pesajes y consumos,
Despiece, Productos derivados, Empaque y etiquetado, Lotes producidos,
Rendimientos, Calidad, Reprocesos, Incidencias, Trazabilidad, Alertas,
Análisis, Auditoría, Configuración, y las 9 de sacrificio futuro) siguen
siendo `MeatProcessingPlaceholderPage` — cero SQL, cero lógica, cero
delegación. Borrar el legacy hoy dejaría esas 18 áreas operativas sin
ninguna forma de usarse desde la UI, aunque el backend detrás exista y
esté probado — exactamente la regresión que la Regla 0 de este proyecto
prohíbe ("NO eliminar funcionalidad operativa sin migración completa").

## Verificación de que el legacy sigue vivo (no es solo teoría)

Reconfirmado por grep directo sobre el árbol actual, no por inferencia —
incluyendo una segunda pasada más profunda que corrigió una suposición
optimista del propio `PROC-0_legacy_audit.md`:

- `interfaz/menu_lateral.py:306` sigue registrando
  `_crear_boton("🔪 Procesamiento Cárnico", "PRODUCCION")`.
  `interfaz/main_window.py:149` importa `from modulos.produccion import
  ModuloProduccion` y `main_window.py:662` lo conecta:
  `self._conectar("PRODUCCION", ModuloProduccion, "🔪 Procesamiento Cárnico")`.
  `MeatProcessingView`/`meat_processing` no aparecen en `main_window.py` en
  absoluto — la UI nueva de PROC-23 no está instanciada por la app en
  ejecución (pinneado por
  `tests/architecture/test_meat_processing_sidebar_navigation.py::test_legacy_produccion_menu_entry_and_module_are_not_touched_yet`,
  en verde).
- **La cadena de llamada real está viva, no solo "importada por un test"**:
  `core/app_container.py` (el contenedor DI que `main.py` construye al
  arrancar la app) instancia directamente `ProductionEngine` (línea 376) y
  `RecipeEngine` (línea 375), y construye `GestionarProduccionUC` +
  `ProductionApplicationService` (líneas 608-619). `modulos/produccion.py`
  usa ese mismo `ProductionApplicationService`. Es decir: el motor legacy
  completo se instancia en cada arranque de la app, esté o no abierta la
  pantalla de Procesamiento.
- `core/services/finance/production_cost_service.py` no es solo "todavía
  importado" — **tiene una suscripción de evento activa**:
  `core/events/wiring.py` registra `ProductionFinanceHandler` (definido en
  `core/events/handlers/production_handler.py`) sobre
  `PRODUCCION_COMPLETADA`/`PRODUCTION_BATCH_CREATED`. Cada vez que el motor
  legacy completa una producción, este handler corre.
- **Corrección a la condición de eliminación de `repositories/recetas.py`
  y `core/services/recipes/*`**: `PROC-0_legacy_audit.md` asumía "cero
  consumidores fuera de `core/services/recipes/` y `modulos/produccion.py`".
  Falso: `core/services/recipes/recipe_resolver.py` es dependencia directa
  de `core/services/sales_fulfillment_service.py` → `sales_service.py` —
  el motor de recetas legacy también sostiene resolución de combos en
  **Ventas**, no solo Procesamiento Cárnico. Retirarlo exige coordinar esa
  migración también (ver `docs/refactor/modules/recetas.md`, corregido en
  esta misma fase).
- `backend/application/use_cases/execute_meat_production_use_case.py` +
  `backend/application/commands/production_commands.py` +
  `backend/application/queries/production_query_service.py` **sí están
  huérfanos de la UI en ejecución** (nada en `interfaz/`/`frontend/`/
  `modulos/` los llama) — pero **no son basura eliminable sin más**:
  `tests/integration/test_phase0_phase1_scaffolding.py` los incluye en una
  lista de ~90 rutas de scaffolding que la FASE 0/1 del refactor completo
  (todo el ERP, no solo Procesamiento) declara obligatorias — el test
  falla si cualquiera de esas ~90 rutas desaparece. Borrar estos tres
  archivos rompería ese guardrail repo-wide sin que esta fase tenga
  contexto para decidir si esa lista debe reducirse; queda fuera de
  alcance seguro.
- `sync/domain_validators/production_validator.py` sigue validando
  `production_batches`/`production_outputs` — tablas que
  `RecipeEngine.ejecutar_produccion` (legacy) sigue escribiendo en cada
  arranque real de la app. No hay tabla legacy huérfana que retirar
  todavía.
- `tests/architecture/allowlists.py` sigue listando `modulos/produccion.py`
  (cupo de 5 violaciones), `repositories/recetas.py` (4),
  `production_application_service.py` (2) y
  `production_cost_service.py` (1) — el ratchet de deuda legacy no se ha
  tocado porque los archivos siguen vivos.

## Precedente correcto: cómo Losses SÍ pudo hacer esto

`docs/refactor/LOSS_23_LEGACY_REMOVAL_REPORT.md` documenta la condición
real que Losses cumplió antes de borrar: su UI nueva (`LossesModuleHost`)
ya cubría el **100%** de las operaciones de la UI legacy
(`modulos/merma.py`), con tablas canónicas (`loss_cases`/`loss_lines`)
recibiendo el 100% de las escrituras y una allowlist de consumidores
legacy que ya estaba vacía antes del corte. Procesamiento Cárnico no está
en ese punto: su allowlist de consumidores legacy (la cadena de arriba)
sigue teniendo exactamente los consumidores que siempre tuvo.

## Limpieza documental (sin riesgo de runtime)

Lo único que esta fase sí cierra es un puntero colgante que el propio
`PROC-0_legacy_audit.md` señaló (`docs/refactor/refactor_state.json`
referencia `modules.RECETAS.report → docs/refactor/modules/recetas.md`,
que nunca existió): se creó `docs/refactor/modules/recetas.md` explicando
dónde vive hoy la fuente de verdad de recetas (`backend/domain/products/`)
sin reclasificar ni tocar el legacy de ejecución de recetas todavía en
uso. **No se modificó** `refactor_state.json` — es infraestructura viva de
otro proceso automatizado (`tools/refactor_control/refactor_orchestrator.py`,
validado por `tests/architecture/test_refactor_state_json_is_valid.py` /
`test_refactor_orchestrator.py`, actualmente en curso sobre otro módulo,
`CONFIGURACION`) — editarlo a mano está fuera del alcance seguro de esta
fase, sin importar lo que el texto original de PROC-0 asumiera sobre él.

## Checklist real para desbloquear PROC-25 (trabajo futuro, no de esta fase)

Para que una futura pasada de PROC-25 pueda de verdad reclasificar algo a
`DELETE`, necesita, en este orden:

1. Construir las 18 páginas funcionales restantes de `MEAT_PROCESSING_NAV`
   (mismo patrón que PROC-23 estableció para Órdenes: query service +
   presenter + página + wiring en `MeatProcessingModuleHost`), cada una
   delegando a los use cases ya construidos en PROC-6..PROC-22.
2. Verificar que ninguna operación que `modulos/produccion.py` expone hoy
   quede sin equivalente en la UI nueva (paridad funcional 1:1, no solo
   "existe un use case parecido").
3. Cortar el sidebar: `interfaz/main_window.py` registra
   `MeatProcessingModuleHost` bajo `"PRODUCCION"`, se retira
   `modulos/produccion.py` de `menu_lateral.py`.
4. Solo entonces: eliminar `modulos/produccion.py`,
   `core/production/production_engine.py`, `core/use_cases/produccion.py`,
   `core/services/production_application_service.py`,
   `sync/domain_validators/production_validator.py` (junto con las tablas
   `production_batches`/`production_outputs`/`production_cost_ledger`), y
   actualizar `tests/architecture/allowlists.py` para retirar esas
   entradas. **`core/services/recipe_engine.py`,
   `core/services/recipes/*` y `repositories/recetas.py` NO entran en este
   paso** — siguen siendo dependencia de Ventas
   (`recipe_resolver.py` ← `sales_fulfillment_service.py`), su retiro
   depende de una migración de recetas en Ventas que esta fase no cubre.
5. `core/services/finance/production_cost_service.py` tiene una condición
   adicional independiente de la UI: requiere un `CostAllocationPort`
   (PROC-22) real conectado a un módulo de Costos — ver
   `PROC-22_costos_finanzas.md`, "Pendiente".

## Pendiente

- Las 18 páginas de UI restantes (ver checklist arriba) — no son trabajo
  de PROC-25, son la condición previa que PROC-25 necesita para poder
  actuar en el futuro.
- `docs/refactor/refactor_state.json` sigue con `RECETAS.report` apuntando
  a un archivo que ahora sí existe (creado en esta fase); su entrada
  `PRODUCCION.report` sigue apuntando a `docs/refactor/modules/produccion.md`,
  que no existe — no se tocó (ver razón arriba); queda documentado aquí
  para quien sí tenga contexto de `tools/refactor_control/` para
  decidir si corregirlo.
