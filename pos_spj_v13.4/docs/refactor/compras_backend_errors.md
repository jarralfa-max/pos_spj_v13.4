# FASE 0 — Inventario de errores backend en Compras

**Fecha:** 2026-05-17
**Regla:** no cambiar comportamiento en esta entrega; documentar rutas y riesgos antes de separar.

---

## 1. Ruta actual `RegistrarCompraUC → PurchaseService.register_purchase()`

`application/use_cases/registrar_compra_uc.py` delega el registro de compra directa a `PurchaseService.register_purchase()`. Esa ruta hoy realiza compra + inventario + finanzas + lotes.

### Side effects de `register_purchase()`

| Side effect | Implementación actual | Severidad si PR/PO lo llama |
|---|---|---|
| Crear compra | `purchase_repo.create_purchase()` | BAJO para DIRECT; CRÍTICO para PR/PO documental si se usa mal. |
| Guardar partidas | `purchase_repo.save_purchase_items()` | BAJO para DIRECT. |
| Inventario | EventBus `PURCHASE_ITEMS_PROCESS` o `inventory_service.add_stock()` | CRÍTICO: PR/PO no deben afectar stock. |
| CXP | `finance_service.crear_cxp()` si hay deuda | CRÍTICO: PR/PO no deben generar CXP. |
| Caja/asiento | `registrar_movimiento_manual()` y `registrar_asiento()` | CRÍTICO: riesgo de doble asiento o asiento antes de recepción. |
| Lotes | `_crear_lotes_compra()` inserta `lotes` y `movimientos_lote`. | CRÍTICO: PR/PO no deben crear lotes. |

---

## 2. Ruta legacy `ProcesarCompraUC`

`core/use_cases/compra.py` está marcado como deprecado y advierte riesgo de doble asiento. Aun así, conserva lógica que:

1. llama `PurchaseService.register_purchase()`;
2. busca `compra_id` por folio;
3. registra asiento inventario/CXP;
4. registra asiento de pago contado;
5. crea CXP si hay deuda;
6. publica evento `COMPRA_REGISTRADA`.

**Riesgo:** si un flujo nuevo PR/PO o una recepción PO usa esta ruta legacy, puede duplicar inventario/finanzas.

---

## 3. SQL directo en UI

`modulos/compras_pro.py` contiene SQL directo en métodos de UI. No se corrige en Fase 1, pero queda prohibido agregar SQL nuevo dentro de widgets.

| Área | Ejemplos | Severidad |
|---|---|---|
| Configuración/roles | consultas genéricas a tablas de configuración. | MEDIO |
| Toolbar documental | carga PR/PO con `container.db.execute()`. | ALTO |
| Proveedores/sucursales/plantillas | carga directa desde UI. | MEDIO |
| Recetas | consulta recetas y actualiza existencia. | CRÍTICO |
| Fallback compra directa | RESUELTO Fase 5: `_fallback_compra_directa()` permanece como stub bloqueado sin SQL ni actualización de inventario. | RESUELTO |

---

## 4. Repositorios existentes a reutilizar

| Archivo | Uso actual/potencial |
|---|---|
| `repositories/purchase_repository.py` | Compra directa e historial de compras. |
| `repositories/purchase_request_repository.py` | Ya existe repositorio documental PR; debe reutilizarse si está disponible. |
| `repositories/purchase_order_repository.py` | Ya existe repositorio PO; debe reutilizarse si está disponible. |
| `application/purchases/*` | Hay comandos/UCs documentales existentes; deben auditarse antes de crear nuevos. |

---

## 5. Reglas backend para fases futuras

| Ruta | Puede afectar inventario | Puede crear lote | Puede crear CXP/asiento | Ruta permitida |
|---|---:|---:|---:|---|
| Compra directa | Sí | Sí si aplica | Sí si aplica | `RegistrarCompraUC` / ruta directa protegida. |
| PR | No | No | No | Use case documental PR. |
| PO | No | No | No | Use case documental PO. |
| Recepción PO | Sí | Sí si aplica | Decisión documentada | `Recepción con QR → adapter → servicios existentes`. |
| QR/contenedor | Sí | Ya existente | Ya existente | Mantener motor actual. |

---

## 6. Condición de parada técnica

Si durante Fases 2-8 se detecta que PR o PO llaman `register_purchase()` o `ProcesarCompraUC.ejecutar()` para crear documentos, debe detenerse el cambio. Esa ruta genera efectos físicos/financieros y no es documental.

## 7. Actualización Fase 5 — compra directa

- La ruta DIRECT autorizada sigue siendo `RegistrarCompraUC → PurchaseService.register_purchase()`.
- `RegistrarCompraUC` rechaza proveedor/sucursal inválidos, carrito vacío, producto/cantidad/costo inválido, subtotal inconsistente, IVA negativo, total inconsistente o forma de pago vacía antes de abrir side effects; el IVA se persiste en la cabecera de compra directa.
- Si inventario falla dentro de `PurchaseService.register_purchase()`, se ejecuta `ROLLBACK TO SAVEPOINT` y no quedan cabecera ni partidas parciales en `compras`/`detalles_compra`.
- La ruta legacy `_fallback_compra_directa()` de la UI quedó bloqueada para evitar doble inventario, doble CXP/asiento, lotes o eventos fuera del orquestador.

## 8. Actualización Fase 6 — separación PR/PO/DIRECT

- PR y PO documentales no deben invocar `RegistrarCompraUC`, `PurchaseService` ni `register_purchase`; solo DIRECT conserva esa ruta física.
- Se detectó que Recepción PO podía duplicar inventario al combinar `inventory_service.add_stock()` con la ruta de compra directa. La recepción PO ahora crea cabecera/partidas de trazabilidad mediante repositorio, sin volver a afectar inventario, lotes, CXP ni asientos.
- Decisión ambigua documentada: la recepción PO de Fase 6 no crea CXP/asiento para evitar duplicidad; la decisión fiscal/contable definitiva debe cerrarse en una fase financiera posterior.


## 9. Actualización Fase 7 — PR/aprobación/PO

- Compra Tradicional puede crear PR en estado `PENDIENTE_APROBACION` sin inventario, kardex, CXP, asientos, lotes ni eventos físicos.
- Aprobar/rechazar PR y convertir a PO se delega a `PurchaseRequestUC`; enviar PO a recepción se delega a `PurchaseOrderUC`.
- La UI documental no debe reabrir SQL para cargar partidas de PR; `PurchaseRequestRepository.get_items()` expone el acceso público para mantener SQL en repositorio.
- Decisión ambigua documentada: Fase 7 no crea CXP/asiento para PR/PO; la afectación financiera queda fuera de la ruta documental y debe resolverse al recibir/facturar sin duplicar efectos.
