# Module Map

## Recommended refactor order

1. Configuración
2. Merma
3. Productos
4. Procesamiento cárnico
5. Transferencias
6. Delivery
7. Caja
8. BI / Dashboard
9. Planeación de compras
10. Cotizaciones
11. Fidelidad / tarjetas
12. Activos
13. Clientes
14. Tickets / etiquetas
15. Hardware
16. Notificaciones
17. WhatsApp pedidos
18. Finanzas
19. RRHH

## Target module connections

All modules should connect through Application Services, Use Cases, QueryServices, and EventBus rather than duplicated UI routes.

## Canonical services by module

| Module | Target services or use cases |
| --- | --- |
| Configuración | `SystemSettingsService`, `ModuleSettingsService`, `CompanyProfileService` |
| Merma | `RegisterWasteUseCase`, `WasteApplicationService`, `WasteQueryService` |
| Productos | `CreateProductUseCase`, `UpdateProductUseCase`, `ProductQueryService` |
| Procesamiento cárnico | `ExecuteMeatProductionUseCase`, `MeatProductionApplicationService` |
| Transferencias | `DispatchTransferUseCase`, `ReceiveTransferUseCase`, `TransferQueryService` |
| Delivery | `CreateDeliveryOrderUseCase`, `AssignDeliveryDriverUseCase`, `DeliveryQueryService` |
| Caja | `OpenCashShiftUseCase`, `RegisterCashMovementUseCase`, `GenerateZCutUseCase` |
| BI / Dashboard | `BusinessIntelligenceQueryService`, metrics services |
| Planeación de compras | `GeneratePurchasePlanUseCase`, `PurchasePlanningService` |
| Cotizaciones | `CreateQuoteUseCase`, `ApproveQuoteUseCase`, `ConvertQuoteToSaleUseCase` |
| Fidelidad / tarjetas | `LoyaltyApplicationService`, `LoyaltyLedgerService`, `LoyaltyCardService` |
| Activos | `CreateAssetUseCase`, `ScheduleMaintenanceUseCase`, `AssetQueryService` |
| Tickets / etiquetas | `TicketTemplateService`, renderers, barcode and QR services |
| Hardware | `ScaleService`, `PrinterService`, `CashDrawerService` |
| Notificaciones | `NotificationRouter`, senders, recipient resolver |
| WhatsApp pedidos | `ParseWhatsAppOrderUseCase`, `CreateOrderFromWhatsAppUseCase` |

## Module completion rule

Each module must be completed one at a time. Do not run broad refactors across unrelated modules in the same phase unless specifically authorized and protected by tests.
