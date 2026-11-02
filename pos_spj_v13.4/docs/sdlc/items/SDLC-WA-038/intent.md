# SDLC-WA-038 — Avisos de Pedidos por WhatsApp ignoran la credencial guardada en Integraciones y solo funcionan con variables de entorno

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §50, §23 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
`OrdersDeliveryWhatsAppClient` construye `WhatsAppClient()` sin conexión. Sin conexión, el cliente solo lee variables de entorno y nunca la credencial que el administrador guardó en Configuración → Integraciones. En una instalación configurada desde la pantalla, "listo para recoger", "va en camino", "entregado" y "ajuste de peso" no se envían.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `backend/infrastructure/integrations/orders_delivery_whatsapp_client.py:30-32` *(verificado directamente)*
- `backend/infrastructure/integrations/whatsapp_client.py:106-125` — `_setting` sin conexión solo lee entorno
- Llamadores: `backend/application/orders_delivery/use_cases/pickup_use_cases.py:65`; `dispatch_use_cases.py:93,215`; `catch_weight_use_cases.py:105`; `substitution_use_cases.py:69`; `customer_notification_use_cases.py:64`
- Prueba: `tests/unit/test_orders_delivery_whatsapp_client.py` (no cubre la fuente de la credencial)

## Impacto
Clientes de Pedidos no reciben avisos aunque el canal esté configurado.

## Objetivo
- El cliente de Pedidos resuelve la credencial por el mismo camino que el resto (SecretStore/Integraciones).
- Prueba: credencial guardada en Integraciones sin variables de entorno → el aviso se envía.

## Alcance
- **Incluye:** Construcción del cliente de Pedidos y su composición.
- **No incluye:** Reintentos (SDLC-ORD-006).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-ORD-006.

## Preguntas abiertas
- Ninguna por ahora.
