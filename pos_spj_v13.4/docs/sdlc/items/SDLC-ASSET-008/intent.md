# SDLC-ASSET-008 — Dominio de Activos: segregación de funciones incompleta y transiciones que saltan el flujo

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §11, §20, §30, §48, §84 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El dominio aplica la regla «quien solicita no aprueba» en la baja, la recepción de transferencia y las diferencias de inventario, pero no en la aprobación de transferencias, de órdenes de trabajo ni de propuestas de capitalización. Una propuesta de capitalización ya aprobada por Finanzas se puede cancelar. `Asset.relocate()` cambia de sucursal sin pasar por una transferencia. `version` nunca se incrementa, así que no sirve para concurrencia optimista. En pérdida o robo la evidencia es opcional y no hay evento para alertar a auditoría.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/asset_transfer.py:76-82` — `approve` sin comparar con `requested_by` (*verificado directamente*); `:116` cancelar en IN_TRANSIT
- `backend/domain/assets/entities/maintenance_work_order.py:101-107` — `approve` sin SoD
- `backend/domain/assets/entities/asset_capitalization_proposal.py:90-94` — sin comparar con `submitted_by`; `:117-124` `cancel` acepta APPROVED (*verificado directamente*)
- `backend/domain/assets/entities/asset.py:140-146` — `relocate()`; `:73` `version` fijo
- `backend/domain/assets/entities/asset_disposal_request.py:49,57` — evidencia opcional; `backend/domain/assets/events.py` sin LOST/STOLEN

## Impacto
Al construir los casos de uso, estas reglas se heredarían rotas: una persona podría aprobar su propia transferencia o capitalización.

## Objetivo
- Solicitante ≠ aprobador en transferencia, OT y capitalización.
- Una propuesta APPROVED o POSTED no se cancela desde Activos.
- Cambiar de sucursal solo es posible por transferencia.
- `version` se incrementa en cada mutación.
- Pérdida/robo exige evidencia y emite evento de alerta.

## Alcance
- **Incluye:** Entidades de `backend/domain/assets/` y sus pruebas unitarias.
- **No incluye:** Persistencia y casos de uso.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-4/5/10/12 (septiembre)

## Preguntas abiertas
- ¿Una transferencia ya en tránsito se puede cancelar (y qué pasa con el activo físico), o solo rechazar al recibir?
