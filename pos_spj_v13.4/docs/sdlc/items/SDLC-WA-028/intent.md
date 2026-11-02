# SDLC-WA-028 — Rechazar una cotización por WhatsApp escribe la tabla legacy de cotizaciones incluso en producción

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §37 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
El botón de rechazo hace `UPDATE cotizaciones SET estado='rechazada'` directo desde el flujo, sin pasar por la guarda de escritura del bridge, así que también escribe en producción. Crear una cotización no tiene clave de idempotencia. Las cotizaciones del canal van a `cotizaciones`/`cotizaciones_detalle`, mientras el contexto Quotes (CRM-43, migraciones 318-320) usa `quotes`/`quote_lines` con `CreateQuoteUseCase`, `AcceptQuoteUseCase`, `RejectQuoteUseCase` y `ConvertQuoteToOrderUseCase`, ninguno llamado por el canal.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/flows/cotizacion_flow.py:140-170,198,226` *(verificado directamente)*
- `whatsapp_service/erp/bridge.py:700-715,849-851`
- `backend/application/quotes/use_cases/quote_use_cases.py:129,333,343`; `convert_quote_use_case.py:56`
- Pruebas: `whatsapp_service/tests/test_cotizacion_flow_phase6.py` (falla hoy); `test_quote_draft_service.py` (canon)

## Impacto
Una cotización de WhatsApp no aparece en Cotizaciones del ERP; el canal escribe datos del ERP en producción.

## Objetivo
- Crear, aceptar, rechazar y convertir cotizaciones por los casos de uso de Quotes, con idempotencia de negocio.
- Ninguna escritura del flujo a tablas del ERP.

## Alcance
- **Incluye:** Flujo de cotización del canal.
- **No incluye:** Contrato general del bridge (SDLC-WA-003).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
CRM-43 (memoria, Quotes construido 2026-10-09).

## Preguntas abiertas
- Ninguna por ahora.
