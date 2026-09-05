# Módulo: Recetas

Estado: **DONE** (superseded — la fuente de verdad se movió)

## Nota (PROC-25, Procesamiento Cárnico)

`docs/refactor/refactor_state.json` referencia este archivo
(`modules.RECETAS.report`) desde una auditoría anterior al pipeline
`PROC-0..PROC-26`; el archivo nunca se había creado, dejando un puntero
colgante. Este documento lo cierra sin modificar `refactor_state.json`
(ese tracker impulsa un proceso automatizado propio, activo y en curso
sobre otro módulo — `current_module` distinto de Procesamiento Cárnico al
momento de escribir esto — y queda fuera de alcance de este pipeline).

## Dónde vive realmente la lógica de recetas hoy

La receta maestra (definición, versión, BOM, esquema de corte, perfil de
rendimiento) es responsabilidad de la capa **Products**, no de
Procesamiento Cárnico ni de un módulo "Recetas" independiente:

- `backend/domain/products/recipe*.py` — entidades y value objects de
  receta.
- Procesamiento Cárnico solo **consume** un snapshot congelado de receta al
  liberar una orden (§14/§40) vía `RecipeSnapshotPort`
  (`backend/application/meat_processing/ports.py`, PROC-6) — nunca
  construye ni edita una receta.

## Legacy aún vivo (no tocado por esta nota)

`repositories/recetas.py`, `core/services/recipe_engine.py` y
`core/services/recipes/{recipe_resolver,recipe_validation_service,recipe_service}.py`
siguen siendo el motor de *ejecución* de receta que usa
`modulos/produccion.py` (vía `RecipeEngine.ejecutar_produccion`), todos
instanciados en `core/app_container.py` — ver
`docs/refactor/PROC-0_legacy_audit.md` (clasificación `BLOCKED`) y
`docs/refactor/PROC-25_legacy_removal_readiness.md` para su condición real
de eliminación. Esta nota documenta dónde vive la fuente de verdad
*objetivo*; no reclasifica ni elimina nada del legacy todavía en uso.

**Corrección importante sobre la condición de eliminación original**: el
audit de PROC-0 asumía "cero consumidores fuera de `core/services/recipes/`
y `modulos/produccion.py`". Una reauditoría en PROC-25 encontró que eso es
**incorrecto**: `core/services/recipes/recipe_resolver.py` es dependencia
viva de `core/services/sales_fulfillment_service.py` (consumido por
`core/services/sales_service.py`) — es decir, el motor de ejecución de
recetas legacy no es exclusivo de Procesamiento Cárnico, también sostiene
resolución de combos/recetas en **Ventas**. Retirarlo requeriría coordinar
con esa migración también, no solo con la de Procesamiento Cárnico —
condición más amplia que la que PROC-0 había documentado.
