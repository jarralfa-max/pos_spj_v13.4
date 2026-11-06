# SDLC-PAY-021 — Contracargos no modelados: sin proceso financiero ni operativo de investigación

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 15 · Fase 10 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 15 «Contracargos» (`ausente`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-019, SDLC-PAY-020

## Problema
No existe ningún concepto de contracargo, mediación o disputa del procesador en el código ni en las pruebas.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- Búsqueda `chargeback|contracargo` sin resultados en `backend/`, `migrations/`, `frontend/`, `tests/` (subagente de Finanzas)

## Impacto
Un contracargo después de conciliar no tiene registro ni asiento; las ventas históricas no deben borrarse.

## Objetivo
- Un contracargo abre un caso de investigación, asienta la retención del procesador y su resolución, sin modificar la venta histórica.
- Pruebas: contracargo después de conciliación.

## Alcance
- **Incluye:** Dominio, asiento, flujo de caso, pruebas.
- **No incluye:** —

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- ¿Quién investiga un contracargo y qué cuentas usa la retención?
