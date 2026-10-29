# SDLC-INV-002 — Captura de peso suma el peso completo al stock y el signo del peso puede invertirse

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
'Capturar peso'/'Reconciliar' postea el peso neto leído completo como `weight_delta` (siempre positivo): cada captura aumenta el peso en stock en lugar de registrar la diferencia. `_post_deltas` toma la dirección del signo de la cantidad y aplica `abs()` a ambos; si cantidad y peso tienen signos opuestos el peso se mueve al revés.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/inventory/use_cases/catch_weight_use_cases.py:79-84`
- `backend/application/inventory/use_cases/adjustment_use_cases.py:85-94`

## Impacto
Inventario por peso (cárnicos) inflado en cada captura.

## Objetivo
- La captura postea sólo la diferencia contra el peso en libros.
- Cantidad y peso conservan cada uno su signo.
- Pruebas con capturas repetidas y correcciones de piezas.

## Alcance
- **Incluye:** Casos de uso de peso variable y ajustes.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria INV.

## Preguntas abiertas
- Ninguna por ahora.
