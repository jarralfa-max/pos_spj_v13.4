# SDLC-CORE-012 — Pruebas de protección del flujo recepción → producción → venta → precio antes de corregirlo

- **Prioridad:** P0
- **Nivel de riesgo:** T0
- **Origen:** `inputs/correcciones.md` C-00 (oleada 0); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §7-§8
- **Estado:** borrador
- **Depende de:** —

## Problema
Las correcciones de la oleada 1 (SDLC-TRF-001, SDLC-TRF-003, SDLC-PROC-002, SDLC-SALES-001) cambian recepción, disponibilidad productiva y precio cobrado. Hoy varias de esas rutas no tienen una prueba que fije su comportamiento actual de punta a punta, así que una corrección podría cambiar algo más sin que nadie lo note.

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- Ya cubierto (pasa hoy): `tests/unit/test_transfers_receipt_use_cases.py` (8 pruebas del caso de uso), `tests/integration/transfers/test_transfer_full_cycle_32cfbf.py`, `tests/integration/meat_processing/test_production_audit_32cfbf.py` (20), `tests/unit/test_sales_inventory_reservation.py:130-194` (reserva idempotente, sin doble retención), `tests/unit/pricing/test_pricing_resolution.py:19-29` (prioridad base/cliente/volumen). Corrida: `110 passed` y `27 passed` (pricing query services, alertas de mínimo, reconstrucción por esquema de corte, ciclo de transferencia).
- **Sin cubrir:** el camino de la pantalla `TransferCycleService.receive` (`backend/application/transfers/cycle_service.py:124-131`) — ninguna prueba fija que hoy arma la línea sin peso, piezas ni lote; la recepción **una vez** produce **una** entrada en el ledger por la ruta UI → servicio; `resolve_sale_price` (`backend/application/sales/pricing_resolution.py:18-28`) no tiene prueba propia (`grep resolve_sale_price tests` = 0 resultados) y nadie fija hoy la caída al catálogo; la disponibilidad de `DirectTransformationQueryService.lots` (`backend/application/meat_processing/queries/direct_transformation_query_service.py:122-162`) con saldos en piezas.
- **`argon2-cffi` ya resuelto — se descarta esa parte de C-00:** está en `requirements.txt:67` (`argon2-cffi>=23.1.0`, desde `6e35244c`), CI lo instala (`.github/workflows/ci-segmented.yml:26`) y el intérprete local tiene 25.1.0 (`docs/sdlc/baseline/2026-10-28.md:4`). La prueba que falló en la auditoría §8 por no tenerlo pasa hoy (`27 passed`, ver arriba).

## Impacto
Sin red de protección, los ítems T0 de la oleada 1 no cumplen "pruebas de regresión antes del cambio" (README, nivel T0).

## Objetivo
- Pruebas de caracterización (estado actual, aunque sea incorrecto, marcadas como tales) para: recibo aceptado → exactamente una entrada; transformación → un consumo y sus salidas; venta → consume solo los SKU reservados; precio resuelto por base/canal/cliente/volumen y el comportamiento actual ante excepción del motor.
- Cada prueba nombra el ítem que la cambiará (TRF-001, TRF-003, PROC-002, SALES-001) para que ese ítem la actualice a propósito, no por accidente.

## Alcance
- **Incluye:** pruebas nuevas en `tests/unit` y `tests/integration`; ningún cambio de código de producción.
- **No incluye:** corregir los defectos (cada uno en su ítem); dependencias nuevas (`argon2-cffi` ya está).

## Restricciones
CLAUDE.md reglas 1 y 16 (regresión antes de refactorizar); `docs/skills/SPJ_REFACTOR_SKILL.md` (UUIDv7 en fixtures desde `backend/shared/ids.py`); pruebas sobre BD en memoria o copia temporal, nunca sobre un `.db` real; QApplication en fixture de módulo (no dentro del cuerpo de la prueba); presupuesto $0; Windows. Nivel T0 por las áreas que fija (transfers, inventory, sales).

## Trabajo previo relacionado
Auditoría 2026-10-26 §7 (plan ejecutable) y §8 (verificación); SDLC-ARQ-TEST-001 (arnés de aceptación multi-terminal) — no lo duplica: aquel es multi-terminal, este es el flujo de una sucursal.

## Preguntas abiertas
- Ninguna.
