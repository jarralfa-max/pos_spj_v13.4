"""PASS 5 — el estado real de la cadena del núcleo ERP.

    Customers → Products → Inventory → Sales → Cash → Finance → Purchases → Transfers

Las piezas de esta cadena están construidas casi todas. Lo que no está es la
conexión, y eso no se ve: cada contexto pasa sus propias pruebas, cada
manejador está escrito y probado, y el efecto entre contextos simplemente no
ocurre. Un archivo de pruebas por contexto no puede detectarlo — por eso este
mide las COSTURAS.

LO QUE LA MEDICIÓN ENCONTRÓ
----------------------------
47 manejadores/puentes definidos; **31 sin ningún consumidor** fuera de su
propio archivo.

Sólo DOS sitios de producción llaman a `subscribe()`. Las tres funciones de
cableado que existen —`wire_procurement`, `wire_pricing`, `wire_logistics`—
**no las llama nadie**, y el arranque (`backend/bootstrap/steps/`) no tiene paso
de cableado: son seis pasos y ninguno suscribe nada.

Hay tres formas distintas de estar oscuro, y conviene no confundirlas porque se
arreglan distinto:

1. SIN SUSCRIPCIÓN. El publicador emite y el manejador existe, pero nadie los
   une. Ej.: `CASH_Z_CUT_GENERATED` lo publica
   `cash_register_application_service.py` y lo escucha `CashShiftClosedHandler`;
   las cargas COINCIDEN (`shift_id`/`branch_id`/`operation_id`). Falta la línea
   que los conecta — y `cash_finance_router.py`, que es justo esa tabla, tampoco
   tiene consumidor.

2. SIN PUBLICADOR REAL. `CashRegisterApplicationService` recibe
   `publisher or (lambda *_: None)`. Nadie le pasa uno, y de hecho **nadie
   construye el servicio en producción**. Los eventos se descartan en una
   lambda vacía sin dejar rastro.

3. CONTRATO DESALINEADO. `sales_outbox` recibe `SALE_COMPLETED` dentro de la
   transacción de la venta —correcto— pero NINGÚN despachador lo lee
   (`SalesOutboxRepository` tiene `list_pending`/`mark_dispatched` sin usar), y
   aunque lo leyera, `SaleCompletedHandler` pide `sale_id`, `settlements`,
   `customer_id` y `folio`, mientras la carga canónica de ventas trae
   `entity_id` y poco más. Conectarlo sin alinear el contrato haría fallar cada
   cobro con "SALE_COMPLETED sin sale_id".

LO QUE SÍ FUNCIONA, Y POR QUÉ IMPORTA NO ROMPERLO
--------------------------------------------------
Ventas→Inventario y Ventas→Caja NO van por el bus: `CheckoutSaleUseCase` llama
directamente a `SalesInventoryClient.confirm()` y a
`SalesCashEffectsClient.record_completed_sale()`. Funcionan.

Por eso la lista de abajo no es una lista de tareas pendientes que haya que
vaciar: suscribir `CanonicalSaleInventoryHandler` o `SaleCompletedCashHandler`
descontaría el inventario y movería la caja DOS VECES por venta, sin ningún
error. Cada manejador oscuro necesita comprobarse contra su vía directa antes
de conectarlo.
"""

from __future__ import annotations

import ast
import re

from .architecture_guardrails import APP_ROOT

_HANDLERS_DIR = APP_ROOT / "backend" / "application" / "event_handlers"

#: Manejadores definidos y sin ningún consumidor, medidos hoy. Sólo puede
#: ENCOGER: conectar uno obliga a retirarlo de aquí, que es lo que convierte la
#: cadena en algo que avanza en vez de un inventario que envejece.
#:
#: Los marcados con ⚠ tienen una vía DIRECTA viva haciendo ya ese efecto:
#: conectarlos duplicaría, no completaría.
DARK_HANDLERS = frozenset({
    # Inventario
    "CanonicalProductionInventoryHandler",
    "CanonicalPurchaseRecipeExplosionHandler",
    "CanonicalPurchaseStockEntryHandler",
    "SlaughterExecutedStubHandler",          # costura futura, SLAUGHTER_ENABLED=False
    # Caja  ⚠ `CheckoutSaleUseCase` ya llama a `SalesCashEffectsClient`
    "SaleCancelledCashHandler",
    "SaleCompletedCashHandler",
    "SaleRefundedCashHandler",
    # RRHH
    "CashShiftClosedAttendanceHandler",
    "CashShiftOpenedAttendanceHandler",
    # Finanzas — instrumentos comerciales
    "CouponExpiredHandler",
    "CouponIssuedHandler",
    "CouponRedeemedHandler",
    "GiftCardRedeemedHandler",
    "GiftCardRefundedHandler",
    "GiftCardSoldHandler",
    "StoredValueAdjustedHandler",
    "VoucherExpiredHandler",
    "VoucherIssuedHandler",
    "VoucherRedeemedHandler",
    # Finanzas — fidelidad
    "LoyaltyPointsExpiredHandler",
    "LoyaltyPointsRedeemedHandler",
    "LoyaltyRewardGrantedHandler",
    "LoyaltyTransactionReversedHandler",
    # Finanzas — operación
    "InventoryAdjustmentHandler",
    "PayrollPaidHandler",
    "ProcurementPayableBridgeHandler",
    "ProductionCompletedHandler",
    "PurchaseReceivedHandler",
    "SaleCompletedHandler",                  # contrato desalineado, ver arriba
    "SaleReversedHandler",
    "WasteRegisteredHandler",
})

#: Funciones de cableado que existen y que nadie llama. Mismo trinquete: llamar
#: a una obliga a retirarla de aquí.
UNCALLED_WIRING = frozenset({
    "wire_logistics",
    "wire_pricing",
    "wire_procurement",
})


def _defined_handlers() -> dict[str, str]:
    encontrados: dict[str, str] = {}
    for path in _HANDLERS_DIR.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and ("Handler" in node.name or "Bridge" in node.name):
                encontrados[node.name] = str(path)
    return encontrados


def _named_outside_its_own_file(nombre: str, origen: str) -> list[str]:
    """Archivos de PRODUCCIÓN que nombran la clase, sin contar el suyo ni los
    `__init__.py` —que sólo re-exportan y no conectan nada— ni las pruebas."""
    usos = []
    for raiz in ("backend", "frontend"):
        for path in (APP_ROOT / raiz).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == "__init__.py":
                continue
            if str(path) == origen:
                continue
            if re.search(rf"\b{nombre}\b", path.read_text(encoding="utf-8", errors="ignore")):
                usos.append(str(path.relative_to(APP_ROOT)))
    return usos


# ── el trinquete ────────────────────────────────────────────────────────────
def test_connecting_a_handler_removes_it_from_the_dark_list():
    """Conectar uno y no anotarlo deja la lista mintiendo.

    Es el error que hace que un inventario de deuda envejezca hasta no decir
    nada: la lista sigue nombrando piezas que ya funcionan y nadie vuelve a
    fiarse de ella.
    """
    definidos = _defined_handlers()
    ya_conectados = sorted(
        nombre for nombre in DARK_HANDLERS
        if nombre in definidos and _named_outside_its_own_file(nombre, definidos[nombre])
    )
    assert not ya_conectados, (
        "Ya tienen consumidor; quítalos de DARK_HANDLERS:\n  " + "\n  ".join(ya_conectados))


def test_no_new_handler_goes_dark():
    """Un manejador nuevo sin consumidor es trabajo que no ocurre.

    No falla, no avisa y pasa sus propias pruebas: el efecto entre contextos
    simplemente no pasa. Esta prueba es lo único que distingue "todavía no se
    conectó" de "se olvidó".
    """
    definidos = _defined_handlers()
    nuevos_oscuros = sorted(
        nombre for nombre, origen in definidos.items()
        if nombre not in DARK_HANDLERS and not _named_outside_its_own_file(nombre, origen)
    )
    assert not nuevos_oscuros, (
        "Manejadores sin ningún consumidor y sin declarar:\n  "
        + "\n  ".join(nuevos_oscuros)
        + "\nConéctalo, o decláralo en DARK_HANDLERS con su motivo.")


def test_the_dark_list_has_no_ghosts():
    definidos = _defined_handlers()
    fantasmas = sorted(DARK_HANDLERS - set(definidos))
    assert not fantasmas, f"Manejadores que ya no existen: {fantasmas}"


def test_wiring_functions_that_nobody_calls_are_declared():
    """Una función de cableado sin llamador es una cadena que no se conecta.

    `wire_procurement` suscribe los traductores de Compras; si nadie la llama,
    Compras no le habla a nadie aunque todo su código esté escrito y probado.
    """
    sin_llamador = set()
    for nombre in UNCALLED_WIRING:
        llamadores = [
            str(p.relative_to(APP_ROOT))
            for raiz in ("backend", "frontend")
            for p in (APP_ROOT / raiz).rglob("*.py")
            if "__pycache__" not in p.parts
            and re.search(rf"\b{nombre}\s*\(", p.read_text(encoding="utf-8", errors="ignore"))
            and not re.search(rf"def\s+{nombre}\s*\(",
                              p.read_text(encoding="utf-8", errors="ignore"))
        ]
        if not llamadores:
            sin_llamador.add(nombre)
    ya_llamadas = sorted(UNCALLED_WIRING - sin_llamador)
    assert not ya_llamadas, (
        "Ya tienen llamador; quítalas de UNCALLED_WIRING:\n  " + "\n  ".join(ya_llamadas))


def test_the_sales_outbox_still_has_no_dispatcher():
    """Fija el eslabón 3 de la cadena, que es el más caro de descubrir tarde.

    `sales_outbox` recibe `SALE_COMPLETED` dentro de la transacción de la venta
    y NADIE lo lee. Cuando alguien escriba `dispatch_sales_outbox`, esta prueba
    empezará a fallar y le obligará a comprobar además el contrato: el
    manejador de Finanzas pide `sale_id`/`settlements`/`customer_id`/`folio` y
    la carga canónica de ventas trae `entity_id`.
    """
    despachadores = [
        p for p in (APP_ROOT / "backend").rglob("*outbox_dispatcher*.py")
        if "__pycache__" not in p.parts
    ]
    de_ventas = [p for p in despachadores if "sales" in p.name]
    assert not de_ventas, (
        "Hay despachador de la bandeja de ventas: comprueba que la carga de "
        "`SALE_COMPLETED` traiga `sale_id`, `settlements`, `customer_id` y "
        "`folio` antes de suscribir `SaleCompletedHandler`, y retira esta "
        "prueba.")
