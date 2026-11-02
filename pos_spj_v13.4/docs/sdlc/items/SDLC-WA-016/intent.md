# SDLC-WA-016 — main.py del microservicio arma todo a mano: abre la base del ERP, migra, registra globals y manipula sys.path en ejecución

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §7, §8, §2 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-007

## Problema
`ApplicationFactory` existe pero no es el punto de entrada. `main.py` crea el bridge sobre la base del ERP, corre migraciones del canal sobre ella, construye parser, matcher, LLM, registro de números, horarios, handoff y routers a mano, registra globals de módulo en los webhooks y monta rutas legacy y v2 a la vez. `sys.path` se modifica en tiempo de ejecución (en cada envío, en el sender). El CompositionRoot pasa el contenedor completo a cada servicio (localizador de servicios) y no construye autenticador del webhook, repositorio de plantillas ni de agentes.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/main.py:24-28,33-79,95-96,110-111,112-113,116-118,121-123,126-160,174-197,201-227`
- `whatsapp_service/bootstrap/application_factory.py:7-17,29-53` — "todavía NO es el entrypoint"
- `sys.path`: `whatsapp_service/erp/bridge.py:62-63,172-173`; `messaging/sender.py:142-143`; `service_host.py:40-41`
- Globals: `whatsapp_service/webhook/whatsapp.py:21-31`; `webhook/mercadopago.py:17-24`; `config/settings.py:63`
- `whatsapp_service/bootstrap/composition_root.py:20-24,199-245`
- Pruebas: `whatsapp_service/tests/test_application_factory.py`, `test_composition_root.py`; no hay prueba de main mínimo

## Impacto
Mantenimiento y seguridad: el arranque depende del orden de importación y de rutas del disco; no se puede probar el servicio armado.

## Objetivo
- `main.py` solo invoca la factory; la factory registra lifespan y routers canónicos.
- Sin `sys.path` en ejecución, sin globals de módulo, sin DDL ni migraciones del ERP al arrancar.
- Los servicios reciben sus dependencias explícitas, no el contenedor.

## Alcance
- **Incluye:** Arranque, composición y empaquetado del microservicio.
- **No incluye:** Migraciones del ERP desde el microservicio (SDLC-WA-007); corte del webhook (SDLC-WA-019).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-4 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
