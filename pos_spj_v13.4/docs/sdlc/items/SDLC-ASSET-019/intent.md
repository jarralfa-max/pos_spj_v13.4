# SDLC-ASSET-019 — El costo real de mantenimiento nunca llega a Finanzas ni a Cuentas por Pagar

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/activos.md` §4, §29, §54 (`/sdlc-plan arquitectura`, 2026-10-29; matriz `docs/sdlc/arquitectura/matriz-activos.md`)
- **Estado:** borrador
- **Depende de:** SDLC-ASSET-016

## Problema
El legacy registraba el costo de mantenimiento y lo pagaba (de forma incorrecta, combinando completar y pagar). Se borró sin reemplazo: hoy el costo real de una OT no se convierte en gasto, CxP ni asiento por ninguna vía. Solo hay costo estimado y real, sin desglose de mano de obra, refacciones y servicio externo, y el evento `MAINTENANCE_COST_CONFIRMED` no lo emite nadie.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Cada ruta:línea fue leída por los subagentes del barrido de `/sdlc-plan arquitectura docs/sdlc/inputs/activos.md` (2026-10-29); las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-activos.md`.

- `backend/domain/assets/entities/maintenance_work_order.py:62-63` — solo estimado/real
- `maintenance_work_order.py:156-169` — `complete()` no emite nada
- `backend/domain/assets/events.py:58` — constante sin productor
- Guardias negativas: `tests/architecture/test_assets_maintenance_does_not_write_finance.py`, `test_assets_do_not_execute_treasury_payments.py`

## Impacto
Gasto de mantenimiento fuera de la contabilidad si se registra en Activos; obliga a capturarlo dos veces.

## Objetivo
- OT completada con desglose de costo en Decimal emite `MAINTENANCE_COST_CONFIRMED` post-commit.
- Finanzas (o Compras, según decisión) lo convierte en gasto/CxP con asiento balanceado; Activos nunca asienta ni paga.
- Prueba de extremo a extremo con balanza cuadrada e idempotencia.

## Alcance
- **Incluye:** Evento, consumidor en Finanzas/Compras, desglose de costo.
- **No incluye:** Capitalización de mejoras (SDLC-ASSET-023).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía el motor contable de Finanzas, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; frontera de `activos.md` §2/§3 (Activos no asienta, no paga, no mueve stock; Finanzas, Compras, Inventario y RRHH son dueños de lo suyo); permisos con la convención del repo `ACTIVOS.<accion>` registrada en `backend/application/assets/permissions.py`, no los `ASSETS_*` literales del documento; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento, revisión independiente obligatoria, migraciones probadas sobre una copia de la BD en el directorio temporal.

## Trabajo previo relacionado
- Memoria Compras: «construye consumidores antes que productores, detrás de cortes numerados» — revisar `event_handlers/` antes de crear

## Preguntas abiertas
- ¿El costo de un servicio externo entra como factura de proveedor en Compras (CxP) o como solicitud de gasto en Finanzas? ¿Qué cuenta de gasto usa el mantenimiento interno?
