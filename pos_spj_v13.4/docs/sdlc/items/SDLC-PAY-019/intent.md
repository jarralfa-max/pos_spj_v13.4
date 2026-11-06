# SDLC-PAY-019 — Sin conciliación de liquidaciones de Mercado Pago: estados CAPTURED→SETTLED→RECONCILED y excepciones

- **Prioridad:** P2
- **Nivel de riesgo:** T0
- **Origen:** `docs/sdlc/inputs/mercado-pago.md` Fase 10.1 (`/sdlc-plan arquitectura` 2026-10-29; matriz `docs/audits/MERCADO_PAGO_INTEGRATION_AUDIT.md`, Fase 10.1 «Ciclo CAPTURED→…» (`ausente`) e «Importación verificable de liquidaciones» (`parcial`))
- **Estado:** aprobado (2026-11-05, Alfred)
- **Depende de:** SDLC-PAY-018, SDLC-PAY-003

## Problema
La conciliación existente es sólo bancaria (estados UNMATCHED…ADJUSTMENT_REQUIRED). No hay ciclo de liquidación del procesador ni estados de excepción (transacción faltante, diferencia, referencia duplicada, comisión desconocida, reembolso parcial, contracargo, revisión manual), ni importación de los reportes oficiales de MP.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por fase con subagentes de lectura; las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/domain/finance/enums.py:217-231`
- `backend/application/use_cases/finance/import_bank_statement_use_case.py:24-65`; `backend/infrastructure/finance/bank_statement_reader.py`; `reconcile_bank_statement_use_case.py:85,101,194`
- Prueba: `tests/integration/finance/test_treasury_reconciliation_budget_assets.py:124-157` (sólo banco)

## Impacto
Tesorería no puede saber qué cobros ya depositó el procesador ni detectar faltantes.

## Objetivo
- Cada cobro capturado recorre CAPTURED → AWAITING_SETTLEMENT → SETTLED → RECONCILED, adaptado al dominio de Finanzas.
- Importación verificable (hash, sin inventar datos) del reporte de liquidación que MP ofrezca; si hay API, por consulta.
- Estados de excepción con revisión manual; reportes por empresa, sucursal, caja, estación, cajero, terminal, cuenta MP, fecha de operación y de liquidación.

## Alcance
- **Incluye:** Dominio de conciliación, importador, reportes, pruebas.
- **No incluye:** Contracargos (PAY-021).

## Restricciones
No desarrollar una aplicación paralela ni duplicar contextos, tablas, servicios o pantallas existentes (`docs/sdlc/inputs/mercado-pago.md` §0-§1); Decimal en todo importe; UUIDv7 desde `backend/shared/ids.py` para identidades internas (los identificadores que exija Mercado Pago se adaptan a su formato); el proveedor no es dueño de la venta, el inventario, las cuentas, la fidelidad, el crédito ni la caja; sin SQL ni operaciones financieras desde widgets; permisos del registro central `MODULO.accion`, nunca por nombre de rol; sin secretos en código, logs, tickets, URLs ni SQLite en claro; ninguna prueba automatizada envía pagos reales; no recuperar código legacy eliminado por suposición; no romper el empaquetado Windows; presupuesto $0. CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, SQL parametrizado fuera de la UI); migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Ninguno además de la matriz.

## Preguntas abiertas
- ¿Qué reporte de liquidación de MP usarán (CSV de «Dinero liberado», API de reportes) y quién lo descarga? CSV 
