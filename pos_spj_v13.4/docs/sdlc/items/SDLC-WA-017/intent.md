# SDLC-WA-017 — /health sin autenticación hace un ping síncrono a Meta en cada llamada y /diagnostics cuenta tablas que el camino vivo no escribe

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §58, §57 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-016

## Problema
Cada `GET /health` abre un cliente HTTP síncrono hacia Graph dentro de un manejador async (bloquea el ciclo de eventos y consume cuota de Meta) y no exige autenticación. El chequeo de la API del ERP solo mira el tipo del cliente. Faltan chequeos de configuración del webhook, plantillas, estado del número y trabajadores vivos. `/diagnostics` cuenta las tablas `whatsapp_*` canónicas, que el camino vivo no escribe: con tráfico real reporta ceros.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/infrastructure/providers/meta_cloud_api/gateway.py:148-171`; `main.py:201`
- `whatsapp_service/bootstrap/health_checks.py:113-140,153-157,233-250`
- `whatsapp_service/application/diagnostics_service.py:43-55`
- Pruebas: `whatsapp_service/tests/test_health_checks.py::test_detail_never_contains_a_secret_value`; `test_diagnostics_service.py`

## Impacto
Operación: monitoreo engañoso y vector de agotamiento de cuota.

## Objetivo
- Chequeos con caché y sin bloquear; endpoint detallado protegido.
- Cada chequeo de §58 mide lo que dice (ping real al ERP, trabajadores vivos).
- Diagnóstico sobre las tablas que el camino vivo escribe.

## Alcance
- **Incluye:** Health y diagnostics del microservicio.
- **No incluye:** Métricas de negocio (SDLC-WA-046).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
WA-4, WA-20 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
