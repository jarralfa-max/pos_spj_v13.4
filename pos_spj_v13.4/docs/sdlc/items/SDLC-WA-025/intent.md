# SDLC-WA-025 — ~170 textos al cliente fijos en código y menú de 3 botones no configurable

- **Prioridad:** P3
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §25, §32 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-022

## Problema
Los flujos, el router y `interactive.py` tienen unos 170 textos fijos, incluida una regla de negocio ("Vigencia: 7 días") escrita en dos lugares. El menú principal son 3 botones fijos; faltan Consultar precios, Seguimiento/Delivery, Puntos y Hablar con una persona. Las listas se cortan a 10 filas sin paginar y el id de categoría se deriva del nombre.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/messaging/interactive.py:12-37,43,61-63,78`
- `whatsapp_service/router/notify_router.py:89`; `application/notification_service.py:56` — "Vigencia: 7 días"
- Ejemplos: `router/message_router.py:100,165`; `flows/pedido_flow.py:260,365-366`; `flows/menu_flow.py:140-149`
- Prueba: `tests/test_wa_flows.py::test_menu_flow_handles_menu_action`

## Impacto
Cada cambio de texto exige liberar el servicio; la vigencia de cotización puede divergir de Quotes.

## Objetivo
- Textos de respuesta versionables y localizables; menú configurable con listas y botones paginados.
- Vigencia y demás reglas se leen del dueño, no del texto.

## Alcance
- **Incluye:** Respuestas conversacionales y menú.
- **No incluye:** Plantillas del proveedor (SDLC-WA-024).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
—

## Preguntas abiertas
- Ninguna por ahora.
