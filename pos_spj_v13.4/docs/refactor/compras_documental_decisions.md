# Decisiones Documentales — Módulo Compras
> Registro de decisiones de arquitectura | 2026-05-15

---

## DEC-001: Ruta oficial de Compra Tradicional

**Decisión:** `RegistrarCompraUC` (en `application/use_cases/registrar_compra_uc.py`) es la ruta canónica para compras DIRECT.

**Alternativas descartadas:**
- `ProcesarCompraUC` (core/use_cases/compra.py): Duplica GL + CXP → DEPRECATED
- Llamada directa a `PurchaseService` desde UI: Viola clean architecture

**Consecuencia:** Todo código nuevo de compra directa llama `RegistrarCompraUC`. El alias `container.uc_compra_tradicional` apunta a `TraditionalPurchaseUC` que lo delega.

---

## DEC-002: PR/PO no afectan inventario

**Decisión:** `PurchaseRequestUC.crear_pr()` y `PurchaseOrderUC.crear_po()` no llaman ningún servicio de inventario, GL ni CXP.

**Fundamento:** PR y PO son compromisos documentales. El inventario se afecta solo en recepción física.

**Verificación:** Tests en `test_purchase_inventory_effects.py`, `test_purchase_finance_effects.py`, `test_receipt_po_contract.py`.

---

## DEC-003: ReceivePOAdapter como único puente PO → Inventario

**Decisión:** El único camino para que una PO afecte inventario es vía `ReceivePOAdapter.register_partial_receipt()`.

**Por qué adapter y no UC directo:** La recepción PO necesita: validar PO, exponer líneas, soportar parciales, comparar esperado vs recibido, actualizar PO y generar compra con GL. Un adapter encapsula esta complejidad sin contaminar los UCs de PO ni la UI QR.

---

## DEC-004: QR NO-TOUCH como política permanente durante Fase 9

**Decisión:** Fase 9 no modifica el motor QR. La recepción de PO permanece como submodo dentro de `📦 3. Recepcionar`, y el historial documental solo consume datos ya generados por los UCs/adapters existentes.

**Justificación:** El flujo QR es operativamente crítico y tiene lógica compleja de contenedores, trazabilidad y recepciones. Fase 9 se limita a visualización documental y filtros de historial, sin duplicar inventario, kardex, CXP, asientos, lotes ni eventos.

**Ver:** `docs/refactor/compras_qr_no_touch_policy.md`

---

## DEC-005: SQL directo en RecepcionQRWidget (no se migra en Fase 9)

**Decisión:** El SQL de mutación en `recepcion_qr_widget.py` (inventario, kardex, trazabilidad) es lógica QR existente y no se mueve en Fase 9.

**Deuda técnica documentada:** En una fase futura se puede extraer a repositorios dedicados con tests de caracterización previos; Fase 9 no lo hace para no tocar motor QR.

---

## DEC-006: Timeline documental con tokens de diseño

**Decisión:** `_refresh_hist_timeline()` debe usar `Colors.*` y `Colors.NEUTRAL.*` para nodos del timeline; no se permiten hex literales ni `background:white`.

**Justificación:** El historial documental debe soportar tema oscuro y claro con el estándar UI del ERP. Los tests de Fase 9 verifican ausencia de colores hardcodeados en los métodos nuevos/modificados.

---

## DEC-007: ProcesarCompraUC marcado DEPRECATED (no eliminado)

**Decisión:** `core/use_cases/compra.py` se marca deprecated pero NO se elimina — tiene referencias activas confirmadas en Fase 10.

**Riesgo:** Si se elimina prematuramente y hay código que lo importa, la app falla en inicio.

**Auditoría Fase 10 (2026-05-17):** `rg` confirmó referencias activas en:

| Archivo | Tipo de referencia | Seguro eliminar |
|---------|-------------------|-----------------|
| `core/app_container.py:424` | `self.uc_compra = ProcesarCompraUC.desde_container(self)` — alias backward compat | ❌ NO — rompe módulos que usen `container.uc_compra` |
| `application/use_cases/__init__.py:3` | re-export shim (intencional, documentado Phase 2) | ❌ NO |
| `tests/test_uc_compra.py` | tests de caracterización del UC deprecated | ✅ Puede eliminarse junto con el UC |
| `tests/purchases/test_purchase_finance_effects.py:25` | usa ProcesarCompraUC para tests de finanzas | ⚠ Migrar a RegistrarCompraUC antes de eliminar |
| `core/events/handlers/purchase_handler.py:73` | solo comentario, no uso real | ✅ Inofensivo |

**Próxima acción (Fase futura):**
1. Migrar `test_purchase_finance_effects.py` para usar `RegistrarCompraUC`
2. Reemplazar `container.uc_compra` en `app_container.py` por alias a `TraditionalPurchaseUC`
3. Solo entonces eliminar `core/use_cases/compra.py`

**Estado:** BLOCKED — no eliminar hasta completar los pasos anteriores.

---

## DEC-008: Columnas faltantes en compras y recepciones

**Decisión:** No agregar `document_type`, `pr_id`, `approved_by` a `compras` ni `purchase_order_id` a `recepciones` hasta Fase 8 o cuando el UI Toolbar Documental las requiera.

**Justificación:** Migraciones mínimas e incrementales. Solo agregar cuando el código las necesite realmente.

---

## DEC-009: ThemeManager no es clase — usar apply_spj_buttons() y Colors.*

**Decisión:** No hay `ThemeManager` como clase. Usar `apply_spj_buttons(widget)` de `spj_styles.py` y `Colors.*` de `design_tokens.py` directamente.

**Código nuevo UI:** Siempre importar Colors desde design_tokens, usar tokens, no hex literales.

---

## DEC-010: Historial como thread (_HistorialLoader)

**Decisión:** El historial de compras se carga en `_HistorialLoader(QThread)` para no bloquear UI. Esta arquitectura se mantiene.

**Columnas actuales del SELECT:** folio, fecha, proveedor, usuario, total, estado, id, condicion_pago, moneda, po_id, po_estado (11 cols → índices 0-10).


---

## DEC-011: Limpieza final Fase 10

**Decisión:** Se elimina `_build_provider_sidebar` porque era código muerto, no estaba conectado a layouts activos y retenía estilos obsoletos.

**Compatibilidad:** Los atributos ocultos que consumen los métodos existentes de proveedores/plantillas permanecen inicializados en `_build_documental_toolbar`; por eso no cambia el flujo DIRECT ni el toolbar documental.

**Límite:** Fase 10 no cambia motor QR, inventario, kardex, CXP, asientos, lotes ni eventos.
