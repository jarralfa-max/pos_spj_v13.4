# SDLC-WA-012 — Cliente de WhatsApp resuelto por los últimos 10 dígitos con LIMIT 1: pedidos y crédito pueden caer en otro cliente

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §12, §13 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** —

## Problema
La identidad del canal es el teléfono crudo y el cliente se busca con `telefono LIKE '%<10 dígitos>' AND activo=1 LIMIT 1` sin orden: si dos clientes comparten sufijo, se toma uno arbitrario y a él se cargan pedidos, crédito y anticipos. El pago de Mercado Pago y la aprobación de ajuste usan el mismo patrón. El normalizador conserva `+521…` distinto de `+52…`, así que un mismo cliente puede tener dos identidades. Hay ~11 implementaciones de normalización o validación de teléfono entre el canal y el ERP. La entidad canónica `WhatsAppIdentity` (estados UNRESOLVED…MERGED) existe pero el camino vivo no la usa.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/erp/bridge.py:291-295` — `LIKE ? ... LIMIT 1` *(verificado directamente)*; lecturas permitidas también en producción
- `whatsapp_service/phone_number.py:30-31` — `521…` se conserva como `+521…` *(verificado directamente)*
- `whatsapp_service/webhook/mercadopago.py:119-121`, `whatsapp_service/erp/adjustment_approval.py:46,65` — mismo sufijo
- `migrations/whatsapp_runtime.py:46` — `conversations.phone TEXT PRIMARY KEY`
- Normalizadores: `backend/domain/customers/value_objects/phone_number.py:12-24`, `backend/domain/hr/value_objects.py:12-25`, `backend/domain/notifications/value_objects/notification_message.py:23`, `backend/infrastructure/integrations/cash_notification_senders.py:24`, `backend/domain/cash_register/configuration.py:169`, políticas de duplicados de CRM, clientes y proveedores
- Canon sin uso vivo: `whatsapp_service/domain/whatsapp/entities/` (identidad), `backend/infrastructure/db/schema/whatsapp_schema.py:119`
- Prueba: `tests/test_wa_bridge.py::test_finds_by_last_10_digits` (fija el sufijo como contrato); ninguna cubre `521`

## Impacto
Clientes y cajeros: un pedido, un anticipo o un pago puede quedar en la cuenta de otra persona; crédito mostrado de otro cliente.

## Objetivo
- Un único normalizador E.164 compartido por canal y ERP; `521…` y `52…` producen la misma identidad.
- La identidad del canal se resuelve por `WhatsAppIdentity` y el teléfono normalizado exacto; un empate queda UNRESOLVED y no se adivina.
- Prueba de dos clientes con el mismo sufijo.

## Alcance
- **Incluye:** Normalizador único, resolución de identidad, búsqueda exacta.
- **No incluye:** Alta de clientes (SDLC-WA-034); maestro único de clientes (SDLC-CRM-003).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
SDLC-CRM-003; WA-2 (memoria).

## Preguntas abiertas
- Ninguna por ahora.
