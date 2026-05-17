# Alcance de Transformación — Módulo Compras
> Versión: 2026-05-15

---

## Resumen de Alcance

| Componente | Modificación permitida | Modificación prohibida |
|-----------|----------------------|----------------------|
| Tab 1: Compra Tradicional | ✅ Lógica documental PR/PO, UI completa, flujo aprobación | Romper flujo DIRECT existente |
| Tab 2: QR / Recepción | ✅ Submodo PO dentro de Recepción (sin pestaña nueva) | Motor QR, lógica de contenedores, inventario QR |
| Tab 3: Histórico | ✅ Filtros, timeline, UI | Analytics pesados, BI, dashboard |
| PurchaseService | ✅ Refactor interno incremental | Cambiar API pública sin wrapper |
| RegistrarCompraUC | ✅ Canónico para DIRECT | No eliminar, no cambiar contrato |
| ProcesarCompraUC (core/use_cases/compra.py) | ✅ Solo mantener wrapper deprecated | No usar en código nuevo |
| TraditionalPurchaseUC | ✅ Router DIRECT/PR/PO | Ya implementado Fases 2-5 |
| ReceivePOAdapter | ✅ Ampliar si hace falta | No duplicar en QR |
| DB Tablas existentes | ✅ Agregar columnas con migración | Cambios destructivos |
| Nuevas tablas | ✅ Solo si no existe equivalente | Tablas paralelas a existentes |

---

## Flujo Documental Objetivo

```
PR (BORRADOR)
  → [Enviar a aprobación] → PR (PENDIENTE_APROBACION)
  → [Aprobar PR]          → PR (APROBADA)
  → [Convertir a PO]      → PR (CONVERTIDA_A_PO) + PO (ABIERTA)
  → [Enviar a recepción]  → Recepción con QR / origen PO
  → [Confirmar recepción] → PO (PARCIAL|RECIBIDA) + compras + inventario + GL
```

```
PR (PENDIENTE_APROBACION)
  → [Rechazar PR]         → PR (RECHAZADA)
  → [Cancelar]            → PR (CANCELADA)
```

```
PO (ABIERTA)
  → [Recepción parcial]   → PO (PARCIAL)
  → [Recepción completa]  → PO (RECIBIDA) → PO (CERRADA)
  → [Cancelar]            → PO (CANCELADA) [sin reversión inventario si no recibida]
```

---

## Reglas de Negocio Invariables

| Regla | Descripción |
|-------|-------------|
| PR-NO-INV | PR NO afecta inventario |
| PR-NO-GL | PR NO genera asiento contable |
| PR-NO-CXP | PR NO genera CXP |
| PO-NO-INV | PO NO afecta inventario |
| PO-NO-GL | PO NO genera GL |
| REC-INV | Recepción SÍ afecta inventario |
| REC-GL | Recepción SÍ puede generar GL (vía PurchaseService en ReceivePOAdapter) |
| REC-LOTES | Recepción SÍ crea lotes |
| NO-DUP-INV | Un mismo artículo de una PO NO puede afectar inventario dos veces |
| NO-DUP-QR | El motor QR no se duplica |
| DIRECT-OK | El flujo DIRECT existente se conserva intacto |

---

## Fases y Estado

| Fase | Nombre | Estado | Archivos principales |
|------|--------|--------|---------------------|
| 0 | Auditoría | ✅ | docs/refactor/ |
| 1 | Tests caracterización | ✅ | tests/purchases/test_*.py |
| 2 | Unificar ruta oficial | ✅ | application/purchases/traditional_purchase_uc.py |
| 3 | Modelo PR | ✅ | application/purchases/purchase_request_uc.py |
| 4 | Modelo PO + Adapter | ✅ | application/purchases/receive_po_adapter.py |
| 5 | UI doc_type selector | ✅ | modulos/compras_pro.py |
| 6 | UI recepción PO como submodo | ✅ | modulos/recepcion_qr_widget.py |
| 7 | UI Historial timeline | ✅ | modulos/compras_pro.py |
| 8 | Recepción QR apta para PO | ✅ | modulos/recepcion_qr_widget.py |
| 9 | Historial documental | ✅ | modulos/compras_pro.py |
| 10 | Pruebas, limpieza y documentación final | ✅ | docs/refactor/, tests/purchases/ |

---

## Criterios de Aceptación Actuales

- [x] App inicia sin errores
- [x] No imports rotos
- [x] Compra DIRECT sin regresión
- [x] QR sin regresión
- [x] PR no afecta inventario
- [x] PO no afecta inventario
- [x] Recepción PO usa ReceivePOAdapter desde submodo interno
- [x] UI respeta Colors.* (sin hex hardcodeados críticos)
- [x] 363+ tests pasando
- [x] Toolbar Documental ERP en Tab 1 (Fase 8)
- [x] Panel de aprobación funcional (Fase 8)
- [x] Botón dinámico según estado/permisos (Fase 8)
- [x] Badge estado PO + columna Δ + panel mermas en submodo PO de Recepcionar (Fase 9)
- [x] Filtro Estado PO en Tab 3 historial (Fase 10)
- [x] CSV exporta todas las columnas desde cache (Fase 10)
- [x] Auditoría ProcesarCompraUC — bloqueado por referencias activas (DEC-007)
