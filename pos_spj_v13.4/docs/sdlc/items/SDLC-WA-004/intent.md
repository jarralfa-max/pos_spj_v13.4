# SDLC-WA-004 — Anticipos por WhatsApp sin asiento y regla de monto que nunca casa

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
Los anticipos van a la tabla legacy `anticipos` (dinero en REAL) y a `ventas.anticipo_pagado`; ningún código del backend lee esa tabla, así que el dinero anticipado por clientes nunca se asienta. La regla de anticipo compara un `Decimal` guardado como TEXT con `BETWEEN` numérico (siempre falso), por lo que todo pedido usa el 50% fijo.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `whatsapp_service/erp/gateways/payment_gateway.py:24-55`; `migrations/m000_base_schema.py:689-692`
- `whatsapp_service/erp/bridge.py:879-886`; `whatsapp_service/domain/money.py:111-115` (inferido de reglas de comparación SQLite, **no ejecutado**)

## Impacto
Dinero de clientes recibido sin registro contable; anticipos cobrados con porcentaje incorrecto.

## Objetivo
- Cada anticipo produce un asiento balanceado (anticipo de clientes) en el contexto dueño.
- La regla de monto se evalúa con Decimal y una prueba cubre cada rango.

## Alcance
- **Incluye:** Registro de anticipo y su asiento; regla de monto.
- **No incluye:** Matching del webhook (WA-001).

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria. Microservicio WhatsApp: preservar los 3 shims de CLAUDE.md regla 9; el cutover del webhook a WA-1..20 sigue diferido por decisión del usuario.

## Trabajo previo relacionado
WA-22.

## Preguntas abiertas
- ¿Cuenta contable de anticipos de clientes?
