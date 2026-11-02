# Matriz de brechas — `mercado-pago.md`

- **Fecha:** 2026-10-29 · **Commit base:** `f119067b` · **Rama:** `sdlc/sdlc-wa-002` (el documento pide `claude/erp-financial-bounded-context-uqxz6b`; HEAD está 7 commits por delante de ella, 0 por detrás).
- **Matriz completa:** [`docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`](../../audits/MERCADO_PAGO_INTEGRATION_AUDIT.md). El documento de requisitos pide ahí su Entregable 1. Esa matriz cumple también el papel de esta: una fila por capacidad, con estado, evidencia ruta:línea, prueba que la cubre, acción (reutilizar/extender/corregir/crear), riesgo e ítem.
- **Método:** `/sdlc-plan arquitectura docs/sdlc/inputs/mercado-pago.md` (modo C). Seis subagentes de lectura agrupados por fase. Las afirmaciones del P0 y de los P1 se volvieron a leer al consolidar.

## Resumen por fase del documento

| Fase | Capacidades | Implementado y funcional | Brechas → ítems |
|---|---|---|---|
| 1.1 / 3 Ventas y contexto de pagos | 14 | 4 | PAY-002, PAY-007, PAY-008, PAY-016, PAY-003; ARQ-IDEM-001/003 (existentes) |
| 1.2 / 9 Caja | 5 | 1 | PAY-003, PAY-005, PAY-006, PAY-023 |
| 1.3 / 10 Finanzas y conciliación | 10 | 2 | PAY-004, PAY-018, PAY-019, PAY-021, PAY-026 |
| 1.5 / 4–8 Proveedor, webhooks, offline | 15 | 0 | PAY-009…PAY-015, PAY-017, PAY-028; WA-001/002 (existentes) |
| 1.4 / 12 / 13.4 / 18 Configuración, seguridad, instalador | 11 | 1 | PAY-022, PAY-023, PAY-024, SEC-006; ARQ-PERM-001, ARQ-INST-003, ARQ-AUD-002 (existentes) |
| 1.6 / 13 UI/UX | 8 | 2 | PAY-013, PAY-015 |
| 14 / 15 WhatsApp, CRM, pedidos, reembolsos | 8 | 2 | PAY-020, PAY-025; WA-004/007, ORD-003 (existentes) |
| 2 / 16 / 17 Diseño, pruebas, documentación | 4 | 0 | PAY-001, PAY-027, PAY-029 |

Los IDs abreviados son `SDLC-<…>`. Los marcados "(existentes)" vienen del triage del 2026-10-28 o de la matriz de arquitectura: se enlazan, no se duplican. SDLC-WA-001 y SDLC-WA-004 se **ampliaron** con evidencia nueva (sección "Ampliación 2026-10-29" de cada intent).

## Orden de dependencias (Fase 20 del documento)

1. Contención inmediata, sin esperar la integración: PAY-002 → PAY-003 → PAY-005 · PAY-006; PAY-004.
2. Diseño y decisiones: PAY-001 (TRD/ADR: dónde viven backend de pagos, token y webhook).
3. Contratos, persistencia e idempotencia: PAY-007 → PAY-008; PAY-023; PAY-024.
4. Backend y seguridad: PAY-022, SEC-006, PAY-009, PAY-010, PAY-011.
5. Point: PAY-012 → PAY-013. Checkout y QR: PAY-014 → PAY-015.
6. Pagos mixtos y offline: PAY-016, PAY-017.
7. Finanzas: PAY-018 → PAY-019. WhatsApp/CRM: PAY-025. Reembolsos y contracargos: PAY-020 → PAY-021.
8. Pruebas, BI, limpieza y documentación: PAY-027, PAY-026, PAY-028, PAY-029.

Cada fase se ejecuta como ítems del SDLC (intent → spec → plan → build → test → deploy), nunca como una corrida larga.
