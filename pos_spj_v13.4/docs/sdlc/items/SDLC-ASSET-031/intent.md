# SDLC-ASSET-031 — Configuración del módulo de Activos ausente (numeración, categorías, SLA, estados) y sin vínculo a dispositivos

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §13, §15, §17, §57, §62 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-010

## Problema
No hay configuración del módulo: formato de folio, categorías, criticidad y SLA, prioridades, avisos. El activo no puede referenciar un dispositivo registrado (por ejemplo, la báscula de Configuración → Dispositivos).

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `frontend/desktop/modules/assets/assets_routes.py:175-177`
- `backend/domain/assets/entities/asset.py:45-75` — sin `device_registration_id`
- `backend/domain/assets/integration_ports.py:52-57` — `DeviceRegistrationLookupPort` sin implementación

## Impacto
Parámetros fijos en código.

## Objetivo
- Configuración de Activos dentro del propio módulo, versionada y auditada.
- Referencia opcional a un dispositivo registrado, sin gestionar su driver.

## Alcance
- **Incluye:** Configuración del módulo y vínculo a dispositivo.
- **No incluye:** Pantallas en Configuración (regla: Configuración no duplica módulos).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- Memoria «Configuración no duplica módulos»

## Preguntas abiertas
- Ninguna por ahora.
