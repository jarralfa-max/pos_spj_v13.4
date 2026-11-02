# SDLC-WA-044 — Sin vocabulario de permisos del canal WhatsApp ni segregación de funciones

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §70, §71 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
Ninguno de los 37 permisos de §70 existe; el catálogo no tiene contexto WHATSAPP. Solo hay códigos por módulo para alertas (`PRODUCTOS.whatsapp.gestionar`, etc.) y `CLIENTES.whatsapp.ver`. El microservicio no tiene identidad de usuario ni RBAC. No hay segregación: resolver un handoff no pide actor ni motivo, no hay reasignación, dead letter no registra quién resolvió, bloquear identidad no guarda causa.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `backend/application/security/permission_catalog.py:58-88` — `_CONTEXT_PERMISSION_MODULES` sin WhatsApp; el archivo no menciona WhatsApp *(verificado directamente)*
- `backend/application/customers/permissions.py:158`; `backend/application/use_cases/configuracion/integration_management_use_cases.py:63-278` (sin actor)
- `whatsapp_service/application/handoff_service.py:72-78`; `backend/infrastructure/db/schema/whatsapp_schema.py:127,245-247`
- Prueba: ninguna

## Impacto
Seguridad: cuando exista la interfaz del canal, no habrá forma de limitar quién responde, configura o ve mensajes sensibles.

## Objetivo
- Permisos del canal registrados en el catálogo con el estándar del repositorio (`WHATSAPP.<accion>`) y verificados en backend con `require()`.
- Roles separados (agente, supervisor, administrador del canal, técnico, de secretos, de plantillas, auditor) con las reglas de §71.

## Alcance
- **Incluye:** Catálogo, sembrado y política de autorización del canal.
- **No incluye:** Autorización de Integraciones en general (SDLC-ARQ-PERM-001).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ARQ-PERM-001; PERM-AUD (memoria).

## Preguntas abiertas
- El documento lista códigos planos (`WHATSAPP_ACCESS`); el estándar del repositorio es `MODULO.accion`. ¿Se usan `WHATSAPP.<accion>` (propuesta) aunque el documento diga otra cosa?
