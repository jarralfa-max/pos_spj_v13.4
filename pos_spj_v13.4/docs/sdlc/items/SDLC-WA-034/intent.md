# SDLC-WA-034 — Cualquier número desconocido se registra como cliente al primer mensaje, sin aviso de privacidad ni consentimiento

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §44 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-012

## Problema
El middleware de identificación manda todo número sin cliente al flujo de registro, que da de alta en `clientes` legacy sin mostrar aviso de privacidad ni pedir consentimiento, y luego crea un puente en `customers` (dos maestros). Además, el chequeo de consentimiento del sender puede crear filas en `customers` en cada envío.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/router/message_router.py:106-119` *(verificado directamente)*; `flows/registro_flow.py:75-90`
- `whatsapp_service/erp/bridge.py:174-178,331-333`
- `whatsapp_service/messaging/sender.py:147` → `backend/application/customers/use_cases/legacy_customer_bridge_use_cases.py:58-61`
- Prueba: `whatsapp_service/tests/test_bridge_create_cliente_minimo.py`

## Impacto
Privacidad y datos: altas sin consentimiento, duplicados entre maestros.

## Objetivo
- El registro muestra el aviso vigente, pide consentimiento y crea el cliente con el caso de uso de Clientes; luego vincula la identidad del canal.
- Ningún envío crea clientes.

## Alcance
- **Incluye:** Flujo de registro y vinculación.
- **No incluye:** Unificar los maestros de clientes (SDLC-CRM-003).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-CRM-003; CRM-9 (privacidad).

## Preguntas abiertas
- ¿Qué datos mínimos pide el registro por WhatsApp y qué versión del aviso de privacidad se muestra? ¿Un número sin registrar puede pedir sin registrarse?
