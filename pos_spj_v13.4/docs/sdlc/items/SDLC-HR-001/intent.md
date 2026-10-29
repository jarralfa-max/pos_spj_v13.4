# SDLC-HR-001 — Nómina asienta faltas y retardos como retenciones por enterar e ignora la cuota patronal

- **Prioridad:** P1
- **Nivel de riesgo:** T0
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El asiento cuadra pero con cuentas equivocadas: `retenciones = bruto + seg. social − neto − préstamos` incluye ABSENCE_DEDUCTION y LATE_DEDUCTION, que se abonan a 'Retenciones y cargas por enterar' (pasivo que nunca se paga) y el gasto de sueldos queda sobrestimado. `PayPayrollRunUseCase` fija `social_security: "0.00"`: la cuota patronal IMSS nunca se provisiona.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/application/event_handlers/finance/payroll_paid_handler.py:37-38,63-66`
- `backend/domain/hr/services/payroll_calculator.py:134,151`; `backend/domain/hr/entities.py:550-565`
- `backend/application/use_cases/hr/payroll_use_cases.py` (payload PAYROLL_PAID ~390)

## Impacto
Estados financieros con pasivo ficticio y costo laboral subestimado.

## Objetivo
- Faltas/retardos reducen el gasto (o se registran según la política) sin crear pasivo.
- Cuota patronal provisionada contra su pasivo.
- Pruebas con nómina que incluya faltas, retardos, préstamos e IMSS.

## Alcance
- **Incluye:** Payload de nómina y handler de Finanzas.
- **No incluye:** Recibos de nómina.

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T0: spec aprobado por escrito, pruebas de regresión antes del cambio, suite completa del segmento y revisión independiente obligatoria.

## Trabajo previo relacionado
Memoria HR-AUD cebf67a.

## Preguntas abiertas
- ¿Cálculo de cuota patronal IMSS: lo hace el sistema o se captura?
