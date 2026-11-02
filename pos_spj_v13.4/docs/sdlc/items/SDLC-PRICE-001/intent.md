# SDLC-PRICE-001 — Cambiar un solo precio de una lista aprobada obliga a duplicar toda la lista

- **Prioridad:** P1
- **Nivel de riesgo:** T1 (la migración de esquema que requiere se trata como T0)
- **Origen:** `inputs/correcciones.md` C-07 (oleada 4); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P1 — Cambiar un único precio obliga a duplicar toda la lista»
- **Estado:** borrador
- **Depende de:** SDLC-SALES-001

## Problema
Una lista activa/aprobada no admite cambios de precio. Para corregir un solo producto, la pantalla ofrece duplicar la lista completa y editar el precio en la copia. El esquema solo permite una fila por lista/producto/sucursal, así que no hay versiones por línea con vigencia, motivo, autor ni aprobador.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `backend/domain/pricing/entities/price_list.py:102-104` — `is_editable` = estado en `EDITABLE_LIST_STATES` (borrador y revisión).
- `frontend/desktop/modules/pricing/pages/product_prices_page.py:165-196` — `_edit`: si la lista es de solo lectura pregunta «¿Duplicar la lista ahora y editar este precio en la copia?» y guarda sobre la copia.
- `backend/infrastructure/db/schema/pricing_schema.py:61` — `UNIQUE(price_list_id, product_id, branch_id)`.

## Impacto
Gerencia comercial: listas duplicadas por cada ajuste, histórico difícil de seguir, riesgo de activar una copia con otros precios cambiados.

## Objetivo
- «Cambiar precio» sobre una lista aprobada crea una revisión de esa línea con vigencia, motivo, autor, aprobador y mínimo, sin reescribir el histórico.
- La consulta canónica de precio elige la versión vigente sin traslapes (prueba de traslape rechazado).

## Alcance
- **Incluye:** revisión por línea, migración de esquema, consulta vigente, UI de «Cambiar precio».
- **No incluye:** asignación de listas por cliente (SDLC-PRICE-002); contrato de resultado de precio hacia Ventas (SDLC-SALES-001).

## Restricciones
CLAUDE.md reglas 1-3 y 13; segregación de funciones de Precios (creador ≠ aprobador, migración 259); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO; migración registrada en `migrations/engine.py` y probada sobre copia de la BD real (ceremonia T0 para esa parte); presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada (obligatoria para la migración).

## Trabajo previo relacionado
Memoria «Proveedores y Precios: capas de escritura» (migraciones 259/260/299: vocabulario `PRECIOS.<accion>`, autorizador en caliente, no activar lista vacía).

## Preguntas abiertas
- ¿Una revisión de línea requiere aprobación de un segundo usuario (como la lista) o basta el permiso de editar precio? · bloquea `/sdlc-design SDLC-PRICE-001`
- ¿Se permite programar una revisión con vigencia futura? · bloquea `/sdlc-design SDLC-PRICE-001`
