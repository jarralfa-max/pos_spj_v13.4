# LOYALTY_LEGACY_ROUTES

Fecha de actualización: 2026-05-27.

## Shim temporal
- `modulos/growth_engine.py` permanece como **shim temporal** para compatibilidad de UI.
- Fecha objetivo de eliminación: **2026-08-31**, condicionada a:
  1) pruebas de fidelidad verdes,
  2) UI migrada a servicios/repo,
  3) cero lecturas de saldo real fuera de `loyalty_ledger`.

## Rutas legacy identificadas
1. `modulos/growth_engine.py` (motor histórico).
2. Cualquier lectura de `clientes.puntos` como saldo real (debe tratarse como snapshot).
3. Consultas directas de `tarjetas_fidelidad` desde UI de ventas.

## Estado FASE 8
- `ventas.py` usa `loyalty_service.resolve_scan(...)` para tarjeta en flujo de scanner.
- `core/services/loyalty_service.py` evita mutar `clientes.puntos` como saldo real en reversas.
- `LOYALTY_LEDGER_SOURCE_OF_TRUTH.md` mantiene decisión canónica de ledger.
