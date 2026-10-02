"""EnterprisePurchasingPresenter — gateway between the enterprise procurement UI
(requisitions, orders, receiving, invoicing, analytics) and the backend.

Wires read/analytics services + use cases; never touches SQL/connections. Maps
results to (ok, message, data) tuples and produces display-ready view models.
"""

from __future__ import annotations

import logging

from backend.application.procurement.ports import (
    BranchWarehouseContextPort,
    InventoryReceiptStatusPort,
    ProcurementFinancePort,
    ProcurementProductCatalogPort,
    SupplierProcurementProfilePort,
)
from backend.shared.ids import new_uuid
from frontend.desktop.components.search_selector import SearchOption
from frontend.desktop.modules.purchasing.capability_resolver import (
    resolve_purchasing_capabilities,
)
from frontend.desktop.modules.purchasing.enterprise_view_models import (
    PurchasingCapabilities,
    TableViewModel,
    invoice_status_es,
    local_datetime_text,
    match_result_es,
    money,
    discrepancy_es,
    order_status_es,
    priority_es,
    receipt_status_es,
    purchase_nature_es,
    requisition_status_es,
    rfq_status_es,
)

def _plain_quantity(value) -> str:
    """Cantidad sin notación científica ni ceros de relleno."""
    from decimal import Decimal, InvalidOperation
    try:
        number = Decimal(str(value if value not in (None, "") else "0"))
    except InvalidOperation:
        return str(value)
    return format(number.normalize(), "f") if number else "0"


logger = logging.getLogger("spj.purchasing.enterprise_presenter")

_PAGE_SIZE = 50


def _supplier_subtitle(row: dict) -> str:
    """Surface a financial block in the picker itself — never let the buyer
    choose a blocked supplier only to find out from a rejected submission."""
    if row.get("bloqueado_financiero"):
        return "Bloqueado financieramente"
    if not row.get("compras_habilitadas", True):
        return "Compras deshabilitadas"
    return row.get("code") or ""


class EnterprisePurchasingPresenter:
    def __init__(self, *, connection_provider, read_services: dict, analytics,
                 use_cases: dict, session_context=None, event_dispatcher=None,
                 logistics_reads=None,
                 warehouse_directory: BranchWarehouseContextPort | None = None,
                 history_reads=None, origin_workspace=None, supplier_picker=None,
                 supplier_origins=None,
                 product_catalog: ProcurementProductCatalogPort | None = None,
                 supplier_profile: SupplierProcurementProfilePort | None = None,
                 supplier_finance: ProcurementFinancePort | None = None,
                 receipt_status: InventoryReceiptStatusPort | None = None) -> None:
        self._conn = connection_provider
        self._reads = read_services
        self._analytics = analytics
        self._use_cases = use_cases
        self._session = session_context
        self._dispatch = event_dispatcher
        self._logistics = logistics_reads
        self._warehouse_directory = warehouse_directory
        self._history = history_reads
        self._origin = origin_workspace
        self._supplier_origins = supplier_origins
        self._suppliers = supplier_picker
        self._product_catalog = product_catalog
        # Wired for future UI consumption (supplier profile/financial standing,
        # goods-receipt posting status); no current presenter flow reads these yet.
        self._supplier_profile = supplier_profile
        self._supplier_finance = supplier_finance
        self._receipt_status = receipt_status
        self._period_start = None
        self._period_end = None

    # session -----------------------------------------------------------------
    def _actor(self) -> str:
        user_id = getattr(self._session, "user_id", None)
        if not user_id:
            raise PermissionError("Se requiere una sesión autenticada de Compras")
        return str(user_id)

    def branch_options(self) -> list[tuple[str, str]]:
        """Sucursales que este usuario PUEDE ver, como `(id, nombre)`.

        NO EXISTÍA. Los dos diálogos de Compras capturaban la sucursal con una
        caja de texto libre, así que para crear una solicitud había que escribir
        a mano el UUID de la sucursal — en la práctica, imposible: el de
        solicitud arranca vacío y no hay forma de elegir.

        El orden es el mismo que exige Transferencias y por el mismo motivo:
        `usuario -> permitidas -> consulta -> resultados`. Listar todas las
        sucursales y dejar que la pantalla oculte las ajenas sería una fuga: el
        dato ya habría viajado y el nombre de una sucursal fuera de alcance se
        descubriría igual.

        Devuelve `[]` si algo falla, nunca revienta el diálogo: sin sucursales
        el combo queda vacío y el backend sigue siendo quien deniega.
        """
        from backend.application.security.branch_scope_query_service import (
            BranchScopeQueryService, BranchSearchQuery,
        )
        if self._conn is None:
            return []
        try:
            encontradas = BranchScopeQueryService(self._conn()).search(
                BranchSearchQuery(allowed_for_user=self._actor(), page_size=200))
        except Exception:
            logger.exception("%s.branch_options failed", type(self).__name__)
            return []
        return [(o.branch_id, o.name) for o in encontradas]

    def default_branch(self) -> str:
        branch_id = (getattr(self._session, "active_branch_id", None)
                     or getattr(self._session, "branch_id", None))
        if not branch_id:
            raise PermissionError("La sesión no tiene una sucursal activa")
        return str(branch_id)

    def default_warehouse(self) -> str:
        warehouse_id = (getattr(self._session, "active_warehouse_id", None)
                        or getattr(self._session, "warehouse_id", None))
        if not warehouse_id:
            raise PermissionError("La sesión no tiene un almacén activo")
        return str(warehouse_id)

    def selected_warehouse(self) -> str | None:
        """Return the explicit warehouse selection without inventing a default."""
        warehouse_id = (getattr(self._session, "active_warehouse_id", None)
                        or getattr(self._session, "warehouse_id", None))
        value = str(warehouse_id or "").strip()
        return value or None

    def warehouse_options(self, branch_id: str | None = None) -> list[tuple[str, str]]:
        """Almacenes que reciben compras en ``branch_id`` (la del formulario; la
        de la sesión si no se da). El mismo directorio que valida el caso de uso,
        así que nunca se ofrece el almacén de otra sucursal."""
        if self._warehouse_directory is None:
            return []
        branch = branch_id or getattr(self._session, "active_branch_id", None)
        if not branch:
            return []
        try:
            return [(str(w), str(label)) for w, label
                    in self._warehouse_directory.active_for_branch(str(branch))]
        except Exception:
            logger.exception("warehouse_options failed")
            return []

    def preselected_warehouse(self, options: list[tuple[str, str]]) -> str:
        """El de la sesión si está entre las opciones; si no, el único; si no, ''."""
        ids = [w for w, _ in options]
        session = str(getattr(self._session, "active_warehouse_id", None) or "")
        if session and session in ids:
            return session
        return ids[0] if len(ids) == 1 else ""

    def supplier_origin_options(self, supplier_id: str | None) -> list[tuple[str, str]]:
        """Bodegas y puntos de recolección del proveedor: ``(id, "Bodega Norte ·
        Querétaro")`` — nunca un UUID capturado a mano."""
        if self._supplier_origins is None or not supplier_id:
            return []
        try:
            return [(o["id"], o["display"])
                    for o in self._supplier_origins.origin_locations(str(supplier_id))]
        except Exception:
            logger.exception("supplier_origin_options failed")
            return []

    def purchase_profile(self, product_id: str):
        """Unidades de compra del producto tal como las define Productos."""
        getter = getattr(self._product_catalog, "purchase_profile", None)
        if getter is None or not product_id:
            return None
        try:
            return getter(str(product_id))
        except Exception:
            logger.exception("purchase profile lookup failed")
            return None

    def product_label(self, product_id: str) -> str:
        """Nombre del producto para mostrar (nunca el id)."""
        resolve = getattr(self._product_catalog, "resolve", None)
        if resolve is None or not product_id:
            return "Producto"
        try:
            option = resolve(str(product_id))
        except Exception:
            logger.exception("product label lookup failed")
            option = None
        return str(option.name) if option is not None and option.name else "Producto"

    def select_warehouse(self, warehouse_id: str) -> None:
        options = dict(self.warehouse_options())
        if warehouse_id not in options:
            raise PermissionError("El almacén no pertenece a la sucursal activa")
        setter = getattr(self._session, "set_warehouse", None)
        if not callable(setter):
            raise PermissionError("La sesión no admite contexto de almacén")
        setter(warehouse_id, options[warehouse_id])

    def session_summary(self) -> dict[str, str | bool]:
        branch_name = str(getattr(self._session, "sucursal_nombre", None)
                          or getattr(self._session, "active_branch_name", None) or "").strip()
        warehouse_name = str(getattr(self._session, "active_warehouse_name", None) or "").strip()
        return {
            "user": str(getattr(self._session, "display_name", None)
                        or getattr(self._session, "nombre_completo", None)
                        or getattr(self._session, "username", None)
                        or getattr(self._session, "usuario", None) or "Sesión activa"),
            "branch": branch_name or "Sucursal sin nombre configurado",
            "warehouse": (warehouse_name if self.selected_warehouse() else
                         "Sin almacén seleccionado"),
            "warehouse_selected": bool(self.selected_warehouse()),
        }

    def can(self, permission: str) -> bool:
        checker = getattr(self._session, "tiene_permiso", None)
        return bool(callable(checker) and checker(permission))

    def capabilities(self) -> PurchasingCapabilities:
        return resolve_purchasing_capabilities(self.can)

    def set_period(self, start_date: str, end_date: str) -> None:
        if start_date > end_date:
            raise ValueError("El periodo inicial no puede ser posterior al final")
        self._period_start, self._period_end = start_date, end_date

    def _scope(self) -> dict:
        return {"branch_id": self.default_branch(), "start_date": self._period_start,
                "end_date": self._period_end}

    def _run(self, key: str, *, operation_id: str | None = None,
             **kwargs) -> tuple[bool, str, dict]:
        try:
            result = self._use_cases[key].execute(
                self._conn(), operation_id=operation_id or new_uuid(), **kwargs)
            data = dict(result.data)
            if result.entity_id is not None:
                data.setdefault("entity_id", result.entity_id)
            if getattr(result, "error_code", None):
                data.setdefault("error_code", result.error_code)
            if result.success and self._dispatch is not None:
                try:
                    self._dispatch()   # post-commit: publish outbox → downstream
                except Exception:
                    logger.exception("post-commit dispatch failed")
            return bool(result.success), result.message, data
        except Exception:
            logger.exception("EnterprisePurchasingPresenter: error in %s", key)
            return False, "Error inesperado; revise el log.", {}

    # ── requisitions ─────────────────────────────────────────────────────────
    def requisitions(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["requisitions"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset,
                        **self._scope())
        total = svc.count(status=status, search=search, **self._scope())
        data, ids = [], []
        for r in rows:
            data.append([r.document_number, r.branch_name, purchase_nature_es(r.purchase_type),
                         priority_es(r.priority), requisition_status_es(r.status),
                         local_datetime_text(r.created_at, date_only=True)])
            ids.append(r.id)
        return TableViewModel(data, ids, total=int(total))

    def requisition_detail(self, requisition_id: str):
        return self._reads["requisitions"].detail(requisition_id)

    def create_requisition(self, **fields) -> tuple[bool, str, dict]:
        return self._run("req_create", actor_user_id=self._actor(), **fields)

    def submit_requisition(self, requisition_id: str) -> tuple[bool, str, dict]:
        return self._run("req_submit", actor_user_id=self._actor(),
                         requisition_id=requisition_id)

    def approve_requisition(self, requisition_id: str, *, approve=True,
                            reason="") -> tuple[bool, str, dict]:
        return self._run("req_approve", approver_user_id=self._actor(),
                         requisition_id=requisition_id, approve=approve, reason=reason)

    def create_rfq_from_requisition(self, requisition_id: str,
                                    supplier_ids: list[str]) -> tuple[bool, str, dict]:
        return self._run("rfq_create", actor_user_id=self._actor(),
                         requisition_id=requisition_id, supplier_ids=supplier_ids)

    # ── quotations (RFQ → cotizaciones → adjudicación) ────────────────────────
    def rfqs(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["rfqs"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset)
        total = svc.count(status=status, search=search)
        data, ids = [], []
        for r in rows:
            data.append([r.document_number, rfq_status_es(r.status), str(r.invited_count),
                         str(r.quoted_count), "Sí" if r.awarded else "No",
                         local_datetime_text(r.created_at, date_only=True)])
            ids.append(r.id)
        return TableViewModel(data, ids, total=int(total))

    def rfq_detail(self, rfq_id: str):
        return self._reads["rfqs"].detail(rfq_id)

    def quote_comparison(self, rfq_id: str):
        return self._reads["rfqs"].comparison(rfq_id)

    def capture_quote(self, **fields) -> tuple[bool, str, dict]:
        return self._run("quote_capture", actor_user_id=self._actor(), **fields)

    def award_quote(self, **fields) -> tuple[bool, str, dict]:
        return self._run("quote_award", actor_user_id=self._actor(), **fields)

    # ── catalog lookups (search-and-pick, never manual id capture) ───────────
    def supplier_options(self, query: str) -> list[SearchOption]:
        if self._suppliers is None:
            return []
        try:
            rows = self._suppliers.search(query)
        except Exception:
            logger.exception("supplier search failed")
            return []
        return [SearchOption(id=r["id"], label=r["name"], subtitle=_supplier_subtitle(r))
                for r in rows]

    def product_options(self, query: str, branch_id: str | None = None) -> list[SearchOption]:
        """Catálogo GLOBAL de compra. La sucursal (la del formulario; la de la
        sesión si no se da) sólo marca los productos no habilitados en ella."""
        if self._product_catalog is None:
            return []
        branch = branch_id or getattr(self._session, "active_branch_id", None) or None
        try:
            options = self._product_catalog.search(query, branch_id=branch)
        except Exception:
            # §35: un fallo técnico (sesión sin sucursal activa, SQL roto) NO
            # puede verse igual que "sin resultados". `EntitySearchInput` ya
            # distingue ambos casos; tragarse la excepción aquí anulaba ese
            # mecanismo y dejaba al comprador mirando una lista vacía sin
            # ninguna pista de que la búsqueda ni siquiera llegó a ejecutarse.
            logger.exception("product search failed")
            raise
        from frontend.desktop.modules.purchasing.direct_purchase_view_models import (
            product_search_option,
        )
        return [product_search_option(o) for o in options]

    def supplier_search_reason(self, query: str) -> str | None:
        """Por qué el buscador de proveedores no devolvió nada.

        Mismo trato que ya tenían los productos: "Sin resultados" no distingue
        "no hay proveedores dados de alta" de "ninguno está aprobado todavía" ni
        de "el término no coincide", y son tres cosas que se arreglan de forma
        distinta. Diagnóstico: nunca lanza.
        """
        explain = getattr(self._suppliers, "explain_empty", None)
        if explain is None:
            return None
        try:
            razon = explain(query)
        except Exception:
            logger.exception("supplier search reason failed")
            return None
        return razon.message if razon is not None else None

    def product_search_reason(self, query: str) -> str | None:
        """Por qué la búsqueda de productos no trajo nada.

        Es un DIAGNÓSTICO: nunca lanza. Un mensaje explicativo que reviente
        dejaría al comprador peor que el genérico "Sin resultados"."""
        explain = getattr(self._product_catalog, "explain_empty", None)
        if explain is None:
            return None
        try:
            return explain(query)   # búsqueda global: la sucursal no explica vacíos
        except Exception:
            logger.exception("product search reason failed")
            return None

    # ── orders ────────────────────────────────────────────────────────────────
    def orders(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["orders"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset,
                        **self._scope())
        total = svc.count(status=status, search=search, **self._scope())
        data, ids = [], []
        for r in rows:
            data.append([r.document_number, r.supplier_name,
                         order_status_es(r.status), f"v{r.version}",
                         money(r.total), local_datetime_text(r.created_at, date_only=True)])
            ids.append(r.id)
        return TableViewModel(data, ids, total=int(total))

    def order_detail(self, order_id: str):
        return self._reads["orders"].detail(order_id)

    def invoice_detail(self, invoice_id: str):
        return self._reads["invoices"].detail(invoice_id)

    def award_orders(self, rfq_id: str) -> dict:
        """Proveedores adjudicados de la RFQ con su orden (si ya existe)."""
        try:
            return self._reads["rfqs"].award_orders(rfq_id) if rfq_id else {}
        except Exception:
            logger.exception("award_orders failed")
            return {}

    def generate_orders_from_award(self, award_id: str, warehouse_id: str, *,
                                   operation_id: str | None = None
                                   ) -> tuple[bool, str, dict]:
        return self._run("po_from_award", operation_id=operation_id,
                         actor_user_id=self._actor(), award_id=award_id,
                         warehouse_id=warehouse_id)

    def create_order(self, *, operation_id: str | None = None,
                     **fields) -> tuple[bool, str, dict]:
        """``operation_id`` estable por captura: reintentar o hacer doble clic
        devuelve la orden ya creada en vez de duplicarla."""
        return self._run("po_create", operation_id=operation_id,
                         actor_user_id=self._actor(), **fields)

    def approve_order(self, order_id: str, *, reason="") -> tuple[bool, str, dict]:
        return self._run("po_approve", approver_user_id=self._actor(),
                         purchase_order_id=order_id, reason=reason)

    def acknowledge_order(self, order_id: str, *, supplier_reference: str = "",
                          confirmed_delivery_date: str | None = None,
                          confirmed_quantities: dict | None = None, comments: str = "",
                          operation_id: str | None = None) -> tuple[bool, str, dict]:
        detail = self.order_detail(order_id)
        labels = ({ln.id: ln.product_name for ln in detail.lines}
                  if detail is not None else {})
        return self._run("po_acknowledge", operation_id=operation_id,
                         actor_user_id=self._actor(), purchase_order_id=order_id,
                         supplier_reference=supplier_reference,
                         confirmed_delivery_date=confirmed_delivery_date,
                         confirmed_quantities=confirmed_quantities or {},
                         comments=comments, line_labels=labels)

    def send_order(self, order_id: str) -> tuple[bool, str, dict]:
        return self._run("po_send", actor_user_id=self._actor(),
                         purchase_order_id=order_id)

    def change_order(self, order_id: str, *, reason, line_changes=None) -> tuple[bool, str, dict]:
        return self._run("po_change", actor_user_id=self._actor(),
                         purchase_order_id=order_id, reason=reason,
                         line_changes=line_changes or [])

    def receive_order(self, order_id: str, *, receipt_lines,
                      has_over_receive_permission=False) -> tuple[bool, str, dict]:
        return self._run("po_receive", actor_user_id=self._actor(),
                         purchase_order_id=order_id, receipt_lines=receipt_lines,
                         has_over_receive_permission=has_over_receive_permission)

    # ── invoices ─────────────────────────────────────────────────────────────
    def invoice_document_options(self, query: str) -> list[SearchOption]:
        svc = self._reads["invoices"]
        try:
            rows = svc.billable_documents(search=query)
        except Exception:
            logger.exception("invoice document search failed")
            return []
        return [SearchOption(id=r["id"], label=r["document_number"],
                             subtitle=r.get("nombre") or "") for r in rows]

    def invoice_document_profile(self, document_id: str) -> dict:
        svc = self._reads["invoices"]
        resolved = svc.resolve_billable_document(document_id)
        if resolved is None:
            return {}
        lines = [dict(line, product_label=self.product_label(str(line["product_id"])))
                 for line in svc.billable_lines(resolved["document_type"], document_id)]
        return {"supplier_id": resolved["supplier_id"],
                "supplier_name": resolved["supplier_name"],
                "document_type": resolved["document_type"], "lines": lines}

    def invoices(self, *, status=None, search="", page=0) -> TableViewModel:
        svc = self._reads["invoices"]
        offset = max(0, page) * _PAGE_SIZE
        rows = svc.list(status=status, search=search, limit=_PAGE_SIZE, offset=offset,
                        **self._scope())
        total = svc.count(status=status, search=search, **self._scope())
        data, ids = [], []
        for r in rows:
            data.append([r.document_number, r.supplier_name,
                         r.invoice_number, money(r.total),
                         invoice_status_es(r.status), match_result_es(r.match_result),
                         local_datetime_text(r.created_at, date_only=True)])
            ids.append(r.id)
        return TableViewModel(data, ids, total=int(total))

    def capture_invoice(self, **fields) -> tuple[bool, str, dict]:
        return self._run("inv_capture", actor_user_id=self._actor(), **fields)

    def match_invoice(self, invoice_id: str) -> tuple[bool, str, dict]:
        return self._run("inv_match", actor_user_id=self._actor(), invoice_id=invoice_id)

    def release_variance(self, invoice_id: str, *, reason,
                         captured_by_user_id: str | None = None) -> tuple[bool, str, dict]:
        # La página no conoce al capturista; antes lo exigía como argumento
        # obligatorio y el botón «Liberar diferencia» reventaba con TypeError.
        if captured_by_user_id is None:
            detail = self.invoice_detail(invoice_id)
            captured_by_user_id = detail.captured_by_user_id if detail else None
        return self._run("inv_release", releaser_user_id=self._actor(),
                         invoice_id=invoice_id, captured_by_user_id=captured_by_user_id,
                         reason=reason)

    def related_shipments(self) -> list[dict]:
        if self._logistics is None:
            return []
        return self._logistics.related_to_destination(
            branch_id=self.default_branch(), warehouse_id=self.default_warehouse())

    # ── compra en origen (Logistics workspace) ───────────────────────────────
    def _origin_run(self, fn, *args, **kwargs) -> tuple[bool, str, dict]:
        try:
            detail = fn(*args, **kwargs)
            return True, "Operación registrada", detail or {}
        except (ValueError, LookupError, PermissionError) as exc:
            return False, str(exc), {}
        except Exception:
            logger.exception("EnterprisePurchasingPresenter: error en compra en origen")
            return False, "Error inesperado; revise el log.", {}

    def origin_documents(self, search: str = "") -> list[dict]:
        if self._origin is None:
            raise PermissionError("Compra en origen no está configurada en este equipo")
        # El almacén destino sale de cada documento; la sesión real no trae almacén.
        return self._origin.documents(branch_id=self.default_branch(),
                                      warehouse_id=self.selected_warehouse() or "",
                                      search=search)

    def origin_workspace(self, shipment_id: str):
        if self._origin is None:
            raise PermissionError("Compra en origen no está configurada en este equipo")
        return self._origin.open(shipment_id)

    def origin_create_shipment(self, document: dict,
                               origin_address_id: str | None = None) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        warehouse = document.get("destination_warehouse_id") or self.selected_warehouse()
        if not warehouse:
            return False, "El documento no tiene almacén destino", {}
        return self._origin_run(self._origin.create_shipment, actor_user_id=self._actor(),
                                branch_id=self.default_branch(), warehouse_id=warehouse,
                                document=document, origin_address_id=origin_address_id)

    def origin_supplier_options(self, supplier_id) -> list[tuple[str, str]]:
        return self._origin.supplier_origin_options(supplier_id) if self._origin else []

    def origin_container_types(self) -> list[tuple[str, str]]:
        return self._origin.container_types() if self._origin else []

    def origin_register_container_type(self, **fields) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_value(self._origin.register_container_type,
                                  actor_user_id=self._actor(), **fields)

    def origin_register_container(self, **fields) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_value(self._origin.register_container,
                                  actor_user_id=self._actor(), **fields)

    def origin_attach_container(self, shipment_id: str, reference: str,
                                parent_node_id: str | None = None) -> tuple[bool, str, dict]:
        return self._origin_run(self._origin.attach_container, actor_user_id=self._actor(),
                                shipment_id=shipment_id, reference=reference,
                                parent_node_id=parent_node_id)

    def origin_loading_lines(self, shipment_id: str) -> list[dict]:
        return self._origin.loading_lines(shipment_id) if self._origin else []

    def origin_assign_line(self, shipment_id: str, **fields) -> tuple[bool, str, dict]:
        return self._origin_run(self._origin.assign_line, actor_user_id=self._actor(),
                                shipment_id=shipment_id, **fields)

    def origin_mark_in_transit(self, shipment_id: str) -> tuple[bool, str, dict]:
        return self._origin_run(self._origin.mark_in_transit, actor_user_id=self._actor(),
                                shipment_id=shipment_id)

    def origin_register_arrival(self, shipment_id: str) -> tuple[bool, str, dict]:
        return self._origin_run(self._origin.register_arrival, actor_user_id=self._actor(),
                                shipment_id=shipment_id)

    def origin_arrival_lines(self, shipment_id: str) -> list[dict]:
        return self._origin.arrival_lines(shipment_id) if self._origin else []

    def origin_record_count(self, shipment_id: str, **fields) -> tuple[bool, str, dict]:
        return self._origin_run(self._origin.record_count, actor_user_id=self._actor(),
                                shipment_id=shipment_id, **fields)

    def origin_receive_and_close(self, shipment_id: str) -> tuple[bool, str, dict]:
        return self._origin_run(self._origin.receive_and_close, actor_user_id=self._actor(),
                                shipment_id=shipment_id)

    def _origin_value(self, fn, **kwargs) -> tuple[bool, str, dict]:
        try:
            value = fn(**kwargs)
        except (ValueError, LookupError) as exc:
            return False, str(exc), {}
        except PermissionError as exc:
            return False, str(exc), {}
        except Exception:
            logger.exception("EnterprisePurchasingPresenter: error en compra en origen")
            return False, "Error inesperado; revise el log.", {}
        return True, "Operación registrada", value if isinstance(value, dict) else {"id": value}

    def origin_mobile_handoff(self, shipment_id: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.mobile_handoff, shipment_id)

    def origin_seal_root(self, shipment_id: str, node_id: str,
                         seal_code: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.seal_root, actor_user_id=self._actor(),
                                shipment_id=shipment_id, node_id=node_id, seal_code=seal_code)

    def origin_dispatch(self, shipment_id: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.dispatch, actor_user_id=self._actor(),
                                shipment_id=shipment_id)

    def origin_authorize_variance(self, shipment_id: str, source_line_id: str,
                                  reason: str) -> tuple[bool, str, dict]:
        if self._origin is None:
            return False, "Compra en origen no está configurada en este equipo", {}
        return self._origin_run(self._origin.authorize_variance, actor_user_id=self._actor(),
                                shipment_id=shipment_id, source_line_id=source_line_id,
                                reason=reason)

    # ── recepciones (página «Pendientes y diferencias») ───────────────────────
    # La página llamaba `receipts()`/`receipt_detail()` y ninguno existía: en
    # producción mostraba «'EnterprisePurchasingPresenter' object has no
    # attribute 'receipts'». Todo sale con nombres y estados en español.
    def receipts(self) -> list[dict]:
        svc = self._reads.get("receipts")
        if svc is None:
            return []
        return [{
            "id": r.id, "document_number": r.document_number,
            "supplier_name": r.supplier_name, "status": receipt_status_es(r.status),
            "received": _plain_quantity(r.received), "accepted": _plain_quantity(r.accepted),
            "rejected": _plain_quantity(r.rejected), "differences": int(r.differences or 0),
            "created_at": local_datetime_text(r.created_at),
        } for r in svc.list(limit=200)]

    def receipt_detail(self, receipt_id: str) -> dict | None:
        from backend.application.procurement.queries.display_refs import (
            ProductDisplayRef, WarehouseDisplayRef,
        )
        svc = self._reads.get("receipts")
        detail = svc.detail(receipt_id) if svc is not None and receipt_id else None
        if detail is None:
            return None
        from backend.application.procurement.queries.display_refs import DisplayRefResolver
        refs = DisplayRefResolver(self._conn())
        products = refs.resolve(ProductDisplayRef, (ln.product_id for ln in detail.lines))
        source = self._receipt_source_number(detail)
        return {
            "document_number": detail.document_number,
            "status": receipt_status_es(detail.status),
            "warehouse": refs.label(WarehouseDisplayRef, detail.warehouse_id),
            "source": source, "created_at": local_datetime_text(detail.created_at),
            "lines": [{
                "id": ln.id, "product": products[ln.product_id].label,
                "ordered_quantity": _plain_quantity(ln.ordered_quantity),
                "received_quantity": _plain_quantity(ln.received_quantity),
                "accepted_quantity": _plain_quantity(ln.accepted_quantity),
                "rejected_quantity": _plain_quantity(ln.rejected_quantity),
                "lot": ln.lot or "—",
            } for ln in detail.lines],
            "differences": [{
                "type": discrepancy_es(d.discrepancy_type),
                "expected": _plain_quantity(d.expected), "actual": _plain_quantity(d.actual),
                "reason": d.reason or "—",
            } for d in detail.differences],
            "invoices": [{
                "id": inv["id"], "document_number": inv["document_number"],
                "invoice_number": inv["invoice_number"],
                "status": invoice_status_es(inv["status"]),
                "match_result": match_result_es(inv.get("match_result"))
                if inv.get("match_result") else "Sin conciliar",
                "total": money(inv["total"]),
            } for inv in detail.invoices],
        }

    @staticmethod
    def _receipt_source_number(detail) -> str:
        if detail.purchase_order_id:
            return f"Orden {detail.source_document_number or ''}".strip()
        if detail.direct_purchase_id:
            return f"Compra directa {detail.source_document_number or ''}".strip()
        return "—"

    # ── documental purchase history ───────────────────────────────────────────
    def purchase_history(self) -> TableViewModel:
        if self._history is None:
            return TableViewModel([], [], 0)
        rows = self._history.canonical_receipts(limit=100)
        data = [[r.document_number, r.supplier_name, r.status,
                 local_datetime_text(r.created_at)] for r in rows]
        return TableViewModel(data, [r.document_number for r in rows], total=len(rows))

    # ── analytics ─────────────────────────────────────────────────────────────
    def analytics_kpis(self):
        return self._analytics.kpis()

    def analytics_charts(self):
        return self._analytics.all_charts()

    def analytics_alerts(self):
        return self._analytics.alerts()

    def navigation_badges(self, kpis) -> dict[str, int]:
        return {
            "requisitions": kpis.open_requisitions,
            "orders": kpis.pending_order_approvals,
            "direct_purchase": kpis.direct_purchases_today,
            "invoices": kpis.invoices_with_differences,
        }
