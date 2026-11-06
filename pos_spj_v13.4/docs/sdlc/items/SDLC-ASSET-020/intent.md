# SDLC-ASSET-020 — Las refacciones de mantenimiento no tienen solicitud a Inventario (reserva y consumo)

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §55 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-ASSET-016

## Problema
§55 pide que las refacciones usadas en una OT se soliciten a Inventario, que reserva y consume. No existe nada de eso: ni solicitud, ni reserva, ni consumo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- No hay `PartsRequest` en `backend/`, `frontend/` ni `tests/` (barrido D)
- `tests/architecture/test_assets_parts_do_not_write_inventory.py` pasa en vacío

## Impacto
Las refacciones se descuentan a mano o no se descuentan.

## Objetivo
- OT genera solicitud de refacciones; Inventario reserva y consume con su propio caso de uso; Activos no toca stock.
- Pruebas de integración.

## Alcance
- **Incluye:** Solicitud y contrato con Inventario.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- SDLC-INV-003 (ubicación de stock por flujo)

## Preguntas abiertas
- ¿Las refacciones salen de un almacén de mantenimiento propio o del almacén general de la sucursal? almacen de mantenimiento 
