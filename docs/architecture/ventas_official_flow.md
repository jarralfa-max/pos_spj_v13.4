# Flujo oficial de ventas (v13.4) — estado objetivo implementado

Fecha: 2026-05-26

## Ruta oficial

1. `modulos/ventas.py` (UI)
2. `core/use_cases/venta.py::ProcesarVentaUC`
3. `core/services/sales_service.py::SalesService.execute_sale`
4. `repositories/sales_repository.py::SalesRepository`
5. `SALE_ITEMS_PROCESS` (strict=True)
6. Handlers transaccionales:
   - `SaleInventoryHandler`
   - `SaleFinanceHandler`
   - `CreditSaleFinanceHandler`
7. `RELEASE SAVEPOINT`
8. `VENTA_COMPLETADA`
9. Handlers post-venta:
   - Loyalty (`loyalty_venta` en wiring)
   - Treasury
   - Audit/Sync/Outbox

## Reglas de arquitectura vigentes

- La UI no ejecuta SQL crítico de cierre de venta.
- La UI no acredita puntos de fidelidad.
- La UI no ejecuta canje real de puntos (solo preview).
- La UI no descuenta inventario de negocio por eventos.
- La UI no registra caja/tesorería de negocio.
- `ProcesarVentaUC` no publica `VENTA_COMPLETADA` ni sync directo.
- `SalesService` no ejecuta fidelidad directa ni notificación/comisiones directas.
- Crédito se valida en backend con normalización canónica de método de pago.
- MercadoPago pendiente no marca venta como completada hasta webhook aprobado.

## MercadoPago pendiente y confirmación

### Creación de intención pendiente
- UI detecta `Mercado Pago`.
- `SalesService.create_pending_payment_sale(...)` guarda intención `pendiente_pago`.
- `MercadoPagoService.crear_link(...)` genera URL de pago.
- UI informa link y no ejecuta venta definitiva.

### Confirmación por webhook
- `MercadoPagoService.procesar_webhook(...)` recibe aprobación.
- Invoca `SalesService.confirm_pending_payment_sale(folio, payment_id)`.
- Se ejecuta venta definitiva por `execute_sale(...)`.
- Se marca intención como `confirmada`.

## Guardrails activos

- `repositories/ventas.py::VentaRepository.create_sale` bloqueado por defecto.
- Solo habilitable con `ALLOW_LEGACY_VENTA_REPOSITORY_WRITES=1`.

## Riesgos residuales (transparentes)

1. Warnings de deprecación existentes (`datetime.utcnow`) en outbox no bloquean flujo, pero deben corregirse en hardening final.
2. La suite global completa sigue mezclando fallas históricas de otros dominios (UI/API) dependientes de infraestructura; se mitiga con CI segmentado por dominio.

## Cierre de riesgos ya mitigados

- Doble acreditación de fidelidad UC/Service: mitigada (handler único + idempotencia ledger).
- Canje pre-pago en UI: mitigado (preview-only + apply backend con venta_id).
- Eventos de inventario de negocio desde UI: mitigado.
- `VENTA_COMPLETADA` duplicado desde UC: mitigado.
- Ruta legacy `VentaRepository` accidental: mitigada por guardrail de entorno.
- Suite E2E encadenada de ventas (contado/crédito/canje/MP pendiente→confirmado): mitigada con `tests/test_sales_no_duplication_real.py`.
- Conversión MP confirmada mantiene `payment_method='Mercado Pago'` para consistencia de reporteo.
