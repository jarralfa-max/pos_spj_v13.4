# SDLC-WA-024 — Plantillas del proveedor en un diccionario fijo: sin versión, categoría, estado ni esquema de parámetros

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §24 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-014

## Problema
Las 9 plantillas de Meta son un diccionario con nombre, idioma y parámetros. No hay categoría (UTILITY/MARKETING/AUTHENTICATION/INTERNAL_OPERATIONAL), versión, ciclo DRAFT…ARCHIVED, id externo, vigencia ni esquema de parámetros; el ERP tiene un catálogo de plantillas de notificación que el microservicio no lee.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/messaging/templates.py:15-61`; `bootstrap/composition_root.py:23` (repositorio "futuro")
- `backend/domain/notifications/entities/notification_template.py:29-37`; `backend/infrastructure/db/schema/notifications_schema.py:42`
- Prueba: `whatsapp_service/tests/test_templates_parameter_validation.py`

## Impacto
Se puede enviar una plantilla no aprobada o con parámetros equivocados; marketing no se distingue de transaccional.

## Objetivo
- Plantillas y versiones persistidas con categoría, estado y esquema de parámetros; solo se envía una versión APPROVED vigente.
- Una sola fuente de plantillas entre ERP y canal.

## Alcance
- **Incluye:** Entidad, tabla, repositorio y validación de envío.
- **No incluye:** Pantalla de administración (SDLC-WA-043).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-17 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
