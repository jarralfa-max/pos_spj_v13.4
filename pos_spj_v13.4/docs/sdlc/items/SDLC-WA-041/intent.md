# SDLC-WA-041 — No existe módulo WhatsApp en el escritorio: nadie puede ver conversaciones ni su estado dentro del ERP

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §49, §65, §66, §67 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-019, SDLC-WA-044

## Problema
El menú lateral tiene 18 módulos y ninguno es WhatsApp; el panel legacy (`modulos/whatsapp/`) se borró sin reemplazo. No hay bandeja, filtros (pendientes, asignadas a mí, esperando cliente/ERP, escaladas, resueltas, bloqueadas), hilo de conversación ni KPIs. El resumen de WhatsApp en el expediente de CRM fija `last_conversation_at=None`, `open_conversations_count=0`, `handoff_pending=False`.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `frontend/desktop/shell/sidebar/migrated_modules_navigation.py:129-231`; no existe `frontend/desktop/modules/whatsapp/`
- `backend/application/customers/queries/customer_whatsapp_summary_query.py:12-26,60-62`
- `whatsapp_service/application/diagnostics_service.py:50-119` — métricas sin interfaz
- Prueba: `tests/integration/customers/test_crm_13_integraciones.py::TestCustomerWhatsAppSummaryQuery` (fija los ceros)

## Impacto
Gerentes y personal no ven lo que pasa en el canal; el expediente del cliente muestra datos falsos.

## Objetivo
- Módulo global WhatsApp con Resumen, Bandeja y Conversaciones según §66, alimentado por consultas del backend (la UI no calcula KPIs).
- Máximo seis KPIs de §67.
- Resumen del expediente con datos reales.

## Alcance
- **Incluye:** Módulo, navegación, bandeja de solo lectura, hilo y KPIs.
- **No incluye:** Composer y respuesta (SDLC-WA-042); configuración técnica (SDLC-WA-043).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-19 (memoria: describía el panel ya borrado); SDLC-UI-* (sistema de diseño).

## Preguntas abiertas
- Ninguna por ahora.
