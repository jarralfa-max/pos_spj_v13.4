# SDLC-WA-043 — Configuración → Integraciones no permite dar de alta cuentas, números por sucursal, plantillas ni enrutamiento de WhatsApp

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §65, §10, §11 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-013, SDLC-WA-044

## Problema
Integraciones es un CRUD genérico: el administrador debe crear a mano una definición `WHATSAPP` (ninguna migración la siembra) y escribir `meta_phone_id` en `config_json` libre. No hay campos de números por sucursal, rol de canal, plantillas ni enrutamiento; el procesador canónico rechaza números no registrados y no hay pantalla ni endpoint para registrarlos.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `frontend/desktop/modules/configuracion/pages/integraciones_page.py:48-433`; `navigation/configuracion_sidebar.py:57-60`
- `tests/integration/configuracion/test_whatsapp_credentials_regression.py:21-24` — la definición solo la crea la prueba
- `whatsapp_service/infrastructure/webhooks/webhook_processor.py:85-91`
- Pruebas: `tests/integration/configuracion/test_whatsapp_credentials_regression.py`

## Impacto
No se puede operar multi-número ni multi-sucursal sin editar la base a mano.

## Objetivo
- Configuración técnica del canal (cuentas, números, secretos, webhook, plantillas, salud, enrutamiento) en Integraciones, con autorización en backend.
- La configuración operativa (conversaciones, agentes, campañas) vive en el módulo WhatsApp, sin duplicarse.

## Alcance
- **Incluye:** Sección técnica de WhatsApp en Integraciones.
- **No incluye:** Autorización en backend de los casos de uso de integraciones (SDLC-ARQ-PERM-001).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ARQ-PERM-001; regla "Configuración no duplica módulos".

## Preguntas abiertas
- Ninguna por ahora.
