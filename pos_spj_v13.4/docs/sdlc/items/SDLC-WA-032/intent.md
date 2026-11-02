# SDLC-WA-032 — Delivery por WhatsApp: dirección solo como texto libre, ubicación compartida ignorada y sincronización de estado siempre falla

- **Prioridad:** P2
- **Nivel de riesgo:** T1
- **Origen:** `docs/sdlc/inputs/whatsapp.md` §41, §42 (`/sdlc-plan arquitectura`, 2026-11-01; matriz `docs/sdlc/arquitectura/matriz-whatsapp.md`)
- **Estado:** borrador
- **Depende de:** SDLC-WA-003

## Problema
La dirección se captura como texto de 5 o más caracteres; la ubicación compartida está declarada pero no se parsea; no hay direcciones guardadas ni confirmación de mapa. Programar delivery hace `UPDATE ventas` con fecha +1 día (solo vía orquestador inactivo). `POST /api/delivery/orders/status` usa `SaleDeliveryProjectionService` con el import comentado: siempre da NameError y devuelve `str(exc)`. Dueños sin uso: `ScheduleOrderUseCase`, `SetOrderDeliveryAddressUseCase`, `AddCustomerAddressUseCase`, zonas y tarifa.

## Evidencia
Rutas relativas a `pos_spj_v13.4/` (las que empiezan con `whatsapp_service/` son relativas a la raíz del repositorio). Cada ruta:línea viene del barrido por grupos de secciones con subagentes de lectura (2026-11-01, HEAD `6816e125`); las marcadas *verificado directamente* se volvieron a leer al consolidar. Lo no comprobado se marca **no verificado**. Matriz completa: `docs/sdlc/arquitectura/matriz-whatsapp.md`.

- `whatsapp_service/router/delivery_router.py:23,216,236-239` *(verificado directamente)*
- `whatsapp_service/flows/pedido_flow.py:224-227`; `models/message.py:17,74-91`
- `whatsapp_service/erp/gateways/delivery_gateway.py:25-30`; `erp/bridge.py:1038-1043`
- `backend/application/orders_delivery/use_cases/scheduled_order_use_cases.py:26`; `address_use_cases.py:32`; `zone_use_cases.py:82`; `backend/application/customers/use_cases/address_use_cases.py:32`; `backend/application/addresses/address_search.py`
- Prueba: `whatsapp_service/tests/test_delivery_request_service.py` (canon); ninguna del router

## Impacto
Entregas con dirección ambigua y sin zona/tarifa validada; el endpoint de estado no sirve.

## Objetivo
- Ubicación compartida, dirección escrita o guardada confirmada con el cliente y registrada por Clientes; Delivery valida zona y tarifa.
- El canal solicita delivery y consulta su seguimiento por casos de uso de Orders/Delivery.
- El endpoint roto se corrige o se retira (sin llamadores).

## Alcance
- **Incluye:** Captura de dirección, solicitud y seguimiento de delivery desde el canal.
- **No incluye:** PWA del repartidor (SDLC-ORD-007).

## Restricciones
`CLAUDE.md` reglas 11-13 (asiento balanceado vía `finance_service.registrar_asiento()` para todo impacto de dinero, sin SQL en UI) y regla 14 (WhatsApp como servicio independiente vía REST + eventos); `docs/skills/SPJ_REFACTOR_SKILL.md` REGLA CERO (UUIDv7 desde `backend/shared/ids.py`, sin lectura ni escritura dual) y rutas dentro de `pos_spj_v13.4/`; migraciones registradas en `migrations/engine.py` y probadas sobre una copia de la base en el directorio temporal, nunca sobre un `.db` real; presupuesto $0; Windows. Nivel T1: pruebas del módulo + `tests/architecture`; revisión independiente recomendada. Los shims que `CLAUDE.md` reglas 8-9 pide preservar ya no existen (ver SDLC-WA-051); el corte del webhook vivo y la eliminación del legacy (WA-21) siguen diferidos por decisión del responsable hasta que se responda la pregunta de SDLC-WA-019.

## Trabajo previo relacionado
ORD-0..30; direcciones estándar (memoria 2026-09-17).

## Preguntas abiertas
- Ninguna por ahora.
