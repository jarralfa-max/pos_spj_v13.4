# SDLC-ASSET-017 — Ninguna orden preventiva se genera sola: sin ciclo por vencimiento, medidores sin persistencia ni avisos

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/activos.md` §23, §39, §107 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-016

## Problema
Nada genera órdenes preventivas cuando un plan vence ni cuando un medidor alcanza su umbral. El disparo por medidor es texto libre. No hay avisos de mantenimiento próximo o vencido en la bandeja.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/repository_ports.py:102`
- `backend/domain/assets/entities/maintenance_plan.py:36` — `meter_trigger` str
- `backend/domain/assets/entities/asset_meter.py:42-49` — solo dominio
- `backend/domain/assets/events.py:67` — `ASSET_METER_READING_RECORDED` sin productor
- `backend/application/notifications/user_inbox_service.py` — no conoce activos

## Impacto
El mantenimiento preventivo depende de la memoria de las personas.

## Objetivo
- Ciclo de fondo idempotente que genera OT por vencimiento y por umbral de medidor.
- Captura de lecturas de medidor.
- Avisos de próximo/vencido en la bandeja.

## Alcance
- **Incluye:** Generación automática, medidores, avisos de mantenimiento.
- **No incluye:** Avisos de garantías y seguros (SDLC-ASSET-022).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: spec breve, pruebas del módulo + `tests/architecture`, revisión independiente recomendada.

## Trabajo previo relacionado
- ASSET-8
- Memoria CRM-43: ciclo de fondo y campana cableados

## Preguntas abiertas
- Ninguna por ahora.
