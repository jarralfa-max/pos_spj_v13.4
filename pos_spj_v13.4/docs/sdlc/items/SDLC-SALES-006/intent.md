# SDLC-SALES-006 — 'Guardar PDF' del ticket ignora el diseñador de Configuración

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** triage 2026-10-28 (`/sdlc-plan triage`, barrido por bounded context + línea base `docs/sdlc/baseline/2026-10-28.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
El ticket impreso usa el layout activo del diseñador; 'Guardar PDF' pasa por el `TicketTemplateEngine` legacy y lee `configuraciones.ticket_template_html`, clave que nadie escribe: el PDF siempre sale con la plantilla por defecto.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea fue leída durante el barrido; las marcadas *verificado directamente* se volvieron a comprobar al consolidar. Lo no comprobado se marca **no verificado**.

- `backend/infrastructure/hardware/sales_ticket_printer.py:64-73`
- `backend/application/sales/use_cases/receipt_use_cases.py:289`
- `backend/infrastructure/integrations/sales_receipt_client.py:227-231`

## Impacto
PDF y ticket impreso distintos.

## Objetivo
- Un solo renderizado a partir del layout activo para impresión y PDF.

## Alcance
- **Incluye:** Recibos.
- **No incluye:** —

## Restricciones
CLAUDE.md reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()`, rastro en `financial_event_log`, sin SQL en UI); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura/escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la BD en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada.

## Trabajo previo relacionado
Memoria TICKET-AUD.

## Preguntas abiertas
- Ninguna por ahora.
