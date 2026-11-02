# SDLC-LOG-002 — No hay bandeja única de recepciones: compras, llegadas de embarque y transferencias se reciben en tres lugares

- **Prioridad:** P1
- **Nivel de riesgo:** T1
- **Origen:** `inputs/correcciones.md` C-09 (oleada 2); auditoría `docs/audits/auditoria_integral_produccion_recepcion_transferencias_productos_precios_2026-10-26.md` §3 «P1 — La bandeja de Transferencias aún no incluye compras»
- **Estado:** borrador
- **Depende de:** SDLC-TRF-001, SDLC-TRF-003

## Problema
Quien recibe mercancía en una sucursal tiene que saber en qué módulo buscar: las compras pendientes están en Compras → Recepciones, las llegadas de compra en origen en la página de Logística de Compras y las transferencias en Transferencias. No hay una sola lista de «lo que me va a llegar».

## Evidencia
Rutas relativas a `pos_spj_v13.4/`. Verificado el 2026-10-31 sobre `4639fed2`.

- `frontend/desktop/modules/purchasing/navigation.py:48-51` — grupo «RECEPCIONES» de Compras (`Pendientes y diferencias`, `Devoluciones y reversos`).
- `frontend/desktop/modules/purchasing/pages/logistics_related_page.py:21,34` — `ArrivalCountDialog` y columnas de llegada; `frontend/desktop/modules/purchasing/enterprise_presenter.py:680-685` — `origin_register_arrival`.
- `frontend/desktop/modules/transfers/pages/base_page.py:147` — `ReceiveTransferDialog` dentro de Transferencias.
- Casos de uso destino existentes: `backend/application/procurement/use_cases/purchase_order_use_cases.py` (`ReceivePurchaseOrderUseCase`), `backend/application/procurement/use_cases/direct_purchase_use_cases.py` (`ReceiveDirectPurchaseUseCase`), `backend/application/transfers/use_cases/transfer_receipt_use_cases.py` (`ConfirmTransferReceiptUseCase`).

## Impacto
Recepcionista/encargado: recepciones olvidadas o hechas en el módulo equivocado; operación lenta en la sucursal.

## Objetivo
- Una bandeja con tipos `Compra` y `Transferencia` alimentada por QueryServices (sin SQL en UI).
- Enrutamiento: OC → `ReceivePurchaseOrderUseCase`; compra sin OC → `ReceiveDirectPurchaseUseCase`; embarque → servicio de llegada de Logística; traslado → `ConfirmTransferReceiptUseCase`.
- Permisos independientes por tipo; solo Compras genera factura/CxP.

## Alcance
- **Incluye:** QueryService agregador de pendientes, página de bandeja, enrutamiento a los casos de uso existentes.
- **No incluye:** cambiar los casos de uso de recepción (TRF-001/TRF-003/PUR-001); SQL de Logística contra tablas ajenas (SDLC-LOG-001).

## Restricciones
CLAUDE.md reglas 7 y 13 (UI sin SQL ni reglas); sin duplicar pantallas (memorias «Configuración no duplica módulos» y «Menú no repite el expediente»): la bandeja reemplaza accesos, no se suma a ellos; componentes canónicos (`StandardTable`, `SearchInput`); presupuesto $0; Windows. Nivel T1 según el responsable; nota: llama casos de uso de `transfers` (T0 en el README) sin cambiarlos.

## Trabajo previo relacionado
SDLC-LOG-001; memoria LOG-INT (módulo Logística, ciclo de transferencia); SDLC-UI-007 (densidad táctil en recepción).

## Preguntas abiertas
- ¿En qué módulo vive la bandeja (Logística, Inventario o una entrada propia «Recepciones»)? ¿Desaparecen los accesos actuales de Compras y Transferencias o quedan como atajo? · bloquea `/sdlc-design SDLC-LOG-002`
