"""ProductsPresenter — bridge between the enterprise products UI and backend.

Wires the read/query services into display-ready view models and
``(ok, message, data)`` tuples. Never touches SQL/connections directly — it calls
a ``read_service_factory`` (an application query service) and the injected backend
services. Presentation-only pages depend on this, so all orchestration/formatting
stays out of Qt.
"""

from __future__ import annotations

import logging

from frontend.desktop.modules.products.view_models import (
    KpiViewModel,
    TableViewModel,
    alerts_table,
    catalog_table,
)

logger = logging.getLogger("spj.products.presenter")


class ProductsPresenter:
    def __init__(self, *, read_service_factory, write_service_factory=None,
                 units_service_factory=None, lifecycle_service_factory=None,
                 code_service_factory=None, categories_read_factory=None,
                 categories_write_factory=None, brands_read_factory=None,
                 brands_write_factory=None, attributes_read_factory=None,
                 attributes_write_factory=None,
                 permission_checker=None, session_context=None) -> None:
        self._read_factory = read_service_factory
        self._write_factory = write_service_factory
        self._units_factory = units_service_factory
        self._lifecycle_factory = lifecycle_service_factory
        self._code_factory = code_service_factory
        self._categories_read = categories_read_factory
        self._categories_write = categories_write_factory
        self._brands_read = brands_read_factory
        self._brands_write = brands_write_factory
        self._attributes_read = attributes_read_factory
        self._attributes_write = attributes_write_factory
        self._has_permission = permission_checker
        self._session = session_context

    # ── ciclo de vida (P0-01/05) ──────────────────────────────────────────
    def activation_readiness(self, product_id: str):
        if self._lifecycle_factory is None:
            return None
        return self._lifecycle_factory()["readiness"].readiness(product_id)

    def submit_product(self, product_id: str) -> tuple[bool, str]:
        return self._run_lifecycle("submit", product_id)

    def activate_product(self, product_id: str) -> tuple[bool, str]:
        return self._run_lifecycle("activate", product_id)

    def _run_lifecycle(self, action: str, product_id: str) -> tuple[bool, str]:
        if self._lifecycle_factory is None:
            return False, "Acción no disponible"
        user_id = getattr(self._session, "user_id", None)
        try:
            result = self._lifecycle_factory()[action].execute(
                product_id=product_id, user_id=user_id or "")
        except Exception as exc:  # noqa: BLE001 — se muestra en la UI
            logger.exception("Acción de ciclo de vida %s falló", action)
            return False, f"Error: {exc}"
        return result.success, result.message

    # ── generación de código (P0-04) ─────────────────────────────────────
    @property
    def can_override_code(self) -> bool:
        """El código manual sólo lo permite PRODUCTS_OVERRIDE_CODE."""
        from backend.application.products.permissions import ProductPermissions
        return self._allowed(ProductPermissions.OVERRIDE_CODE)

    def preview_code(self, *, product_type: str,
                     category_id: str | None = None) -> str | None:
        """Vista previa del código automático (no consume la secuencia)."""
        if self._code_factory is None:
            return None
        try:
            return self._code_factory().preview(
                product_type=product_type, category_id=category_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo previsualizar el código")
            return None

    # ── categorías jerárquicas (P1-01) ────────────────────────────────────
    @property
    def can_manage_categories(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._categories_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.CATEGORIES_MANAGE))

    def list_categories(self) -> list[dict]:
        """Opciones planas (sangradas) para el selector de categoría del formulario."""
        if self._categories_read is None:
            return []
        try:
            return self._categories_read().flat_options(active_only=True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar categorías")
            return []

    def category_tree(self) -> list[dict]:
        if self._categories_read is None:
            return []
        try:
            return self._categories_read().tree()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo cargar el árbol de categorías")
            return []

    def get_category(self, category_id: str) -> dict | None:
        if self._categories_read is None:
            return None
        try:
            return self._categories_read().get(category_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener la categoría")
            return None

    def save_category(self, *, category_id: str | None, code: str, name: str,
                      parent_id: str | None = None, sort_order: int = 0
                      ) -> tuple[bool, str, str | None]:
        if self._categories_write is None:
            return False, "Sin permisos de gestión de categorías", None
        from backend.application.products.commands.product_category_commands import (
            CreateCategoryCommand,
            UpdateCategoryCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._categories_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if category_id:
                res = ucs["update"].execute(UpdateCategoryCommand(
                    operation_id=new_uuid(), category_id=category_id, code=code,
                    name=name, sort_order=sort_order, user_id=user_id))
            else:
                res = ucs["create"].execute(CreateCategoryCommand(
                    operation_id=new_uuid(), code=code, name=name,
                    parent_id=parent_id, sort_order=sort_order, user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Guardado de categoría falló")
            return False, f"Error: {exc}", None
        return res.success, res.message, res.category_id

    def move_category(self, category_id: str,
                      new_parent_id: str | None) -> tuple[bool, str]:
        return self._run_category("move", category_id, new_parent_id=new_parent_id)

    def set_category_active(self, category_id: str, active: bool) -> tuple[bool, str]:
        return self._run_category("set_active", category_id, active=active)

    def _run_category(self, action: str, category_id: str, **kw) -> tuple[bool, str]:
        if self._categories_write is None:
            return False, "Sin permisos de gestión de categorías"
        from backend.application.products.commands.product_category_commands import (
            MoveCategoryCommand,
            SetCategoryActiveCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._categories_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "move":
                cmd = MoveCategoryCommand(
                    operation_id=new_uuid(), category_id=category_id,
                    new_parent_id=kw.get("new_parent_id"), user_id=user_id)
            else:
                cmd = SetCategoryActiveCommand(
                    operation_id=new_uuid(), category_id=category_id,
                    active=bool(kw.get("active")), user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de categoría %s falló", action)
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── marcas (P1-02) ─────────────────────────────────────────────────────
    @property
    def can_manage_brands(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._brands_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.BRANDS_MANAGE))

    def list_brands(self) -> list[dict]:
        """Opciones para el selector de marca del formulario (activas)."""
        if self._brands_read is None:
            return []
        try:
            return self._brands_read().options(active_only=True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar marcas")
            return []

    def brand_catalog(self) -> list[dict]:
        if self._brands_read is None:
            return []
        try:
            return self._brands_read().list_brands()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo cargar el catálogo de marcas")
            return []

    def get_brand(self, brand_id: str) -> dict | None:
        if self._brands_read is None:
            return None
        try:
            return self._brands_read().get(brand_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener la marca")
            return None

    def save_brand(self, *, brand_id: str | None, code: str, name: str,
                   description: str | None = None) -> tuple[bool, str, str | None]:
        if self._brands_write is None:
            return False, "Sin permisos de gestión de marcas", None
        from backend.application.products.commands.product_brand_commands import (
            CreateBrandCommand,
            UpdateBrandCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._brands_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if brand_id:
                res = ucs["update"].execute(UpdateBrandCommand(
                    operation_id=new_uuid(), brand_id=brand_id, code=code, name=name,
                    description=description, user_id=user_id))
            else:
                res = ucs["create"].execute(CreateBrandCommand(
                    operation_id=new_uuid(), code=code, name=name,
                    description=description, user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Guardado de marca falló")
            return False, f"Error: {exc}", None
        return res.success, res.message, res.brand_id

    def set_brand_active(self, brand_id: str, active: bool) -> tuple[bool, str]:
        if self._brands_write is None:
            return False, "Sin permisos de gestión de marcas"
        from backend.application.products.commands.product_brand_commands import (
            SetBrandActiveCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._brands_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            res = ucs["set_active"].execute(SetBrandActiveCommand(
                operation_id=new_uuid(), brand_id=brand_id, active=active,
                user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Activación de marca falló")
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── atributos (P1-03) ──────────────────────────────────────────────────
    @property
    def can_manage_attributes(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._attributes_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.ATTRIBUTES_MANAGE))

    def attribute_catalog(self) -> list[dict]:
        if self._attributes_read is None:
            return []
        try:
            return self._attributes_read().list_attributes()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo cargar el catálogo de atributos")
            return []

    def get_attribute(self, attribute_id: str) -> dict | None:
        if self._attributes_read is None:
            return None
        try:
            return self._attributes_read().get(attribute_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener el atributo")
            return None

    def list_attribute_options(self, attribute_id: str) -> list[dict]:
        if self._attributes_read is None:
            return []
        try:
            return self._attributes_read().list_options(attribute_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar opciones")
            return []

    def save_attribute(self, *, attribute_id: str | None, code: str, name: str,
                       data_type: str = "LIST") -> tuple[bool, str, str | None]:
        if self._attributes_write is None:
            return False, "Sin permisos de gestión de atributos", None
        from backend.application.products.commands.product_attribute_commands import (
            CreateAttributeCommand,
            UpdateAttributeCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._attributes_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if attribute_id:
                res = ucs["update"].execute(UpdateAttributeCommand(
                    operation_id=new_uuid(), attribute_id=attribute_id, code=code,
                    name=name, user_id=user_id))
            else:
                res = ucs["create"].execute(CreateAttributeCommand(
                    operation_id=new_uuid(), code=code, name=name,
                    data_type=data_type, user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Guardado de atributo falló")
            return False, f"Error: {exc}", None
        return res.success, res.message, res.entity_id

    def set_attribute_active(self, attribute_id: str,
                             active: bool) -> tuple[bool, str]:
        if self._attributes_write is None:
            return False, "Sin permisos de gestión de atributos"
        from backend.application.products.commands.product_attribute_commands import (
            SetAttributeActiveCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._attributes_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            res = ucs["set_active"].execute(SetAttributeActiveCommand(
                operation_id=new_uuid(), attribute_id=attribute_id, active=active,
                user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Activación de atributo falló")
            return False, f"Error: {exc}"
        return res.success, res.message

    def save_attribute_option(self, *, option_id: str | None, attribute_id: str,
                              code: str, label: str, sort_order: int = 0,
                              active: bool = True) -> tuple[bool, str, str | None]:
        if self._attributes_write is None:
            return False, "Sin permisos de gestión de atributos", None
        from backend.application.products.commands.product_attribute_commands import (
            AddAttributeOptionCommand,
            UpdateAttributeOptionCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._attributes_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if option_id:
                res = ucs["update_option"].execute(UpdateAttributeOptionCommand(
                    operation_id=new_uuid(), option_id=option_id, code=code,
                    label=label, sort_order=sort_order, active=active,
                    user_id=user_id))
            else:
                res = ucs["add_option"].execute(AddAttributeOptionCommand(
                    operation_id=new_uuid(), attribute_id=attribute_id, code=code,
                    label=label, sort_order=sort_order, user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Guardado de opción falló")
            return False, f"Error: {exc}", None
        return res.success, res.message, res.entity_id

    def list_units(self) -> list[dict]:
        """Unidades del catálogo para el selector del formulario (P0-03)."""
        if self._units_factory is None:
            return []
        try:
            return self._units_factory().list_units()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar unidades")
            return []

    # ── alta / edición del maestro (PROD-19 7b) ───────────────────────────
    @property
    def can_write(self) -> bool:
        return self._write_factory is not None

    def _allowed(self, canonical_code: str) -> bool:
        """Permiso granular canónico (PROD-19 paso 8). Sin verificador → permisivo
        (compat: el gating del menú ya restringió el acceso al módulo)."""
        if self._has_permission is None:
            return self.can_write
        return self.can_write and bool(self._has_permission(canonical_code))

    @property
    def can_create(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        return self._allowed(ProductPermissions.CREATE)

    @property
    def can_edit(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        return self._allowed(ProductPermissions.EDIT)

    def get_product(self, product_id: str) -> dict | None:
        """Fila del maestro para prellenar el formulario de edición."""
        if not self.can_write:
            return None
        create_uc, update_uc, repo = self._write_factory()
        return repo.get(product_id)

    def save_product(self, *, product_id: str | None, fields: dict) -> tuple[bool, str, str | None]:
        """Alta (product_id None) o edición. Devuelve (ok, mensaje, product_id)."""
        if not self.can_write:
            return False, "Sin permisos de escritura", None
        from backend.application.products.commands.product_master_commands import (
            CreateProductMasterCommand,
            UpdateProductMasterCommand,
        )
        from backend.shared.ids import new_uuid

        user_id = getattr(self._session, "user_id", None)
        create_uc, update_uc, _repo = self._write_factory()
        try:
            if product_id:
                cmd = UpdateProductMasterCommand(
                    operation_id=new_uuid(), user_id=user_id, product_id=product_id, **fields)
                result = update_uc.execute(cmd)
            else:
                cmd = CreateProductMasterCommand(
                    operation_id=new_uuid(), user_id=user_id, **fields)
                result = create_uc.execute(cmd)
        except Exception as exc:  # noqa: BLE001 — el error se muestra en la UI
            logger.exception("Guardado de producto falló")
            return False, f"Error: {exc}", None
        return result.success, result.message, result.product_id

    # ── overview (§43) ────────────────────────────────────────────────────
    def overview_kpis(self) -> list[KpiViewModel]:
        try:
            counts = self._read_factory().overview_counts()
        except Exception:  # pragma: no cover - defensive; UI shows empty state
            logger.exception("No se pudieron obtener KPIs de productos")
            return []
        return [
            KpiViewModel("active", "Productos activos", str(counts["active"]), "success"),
            KpiViewModel("meat", "Productos cárnicos", str(counts["meat"]), "info"),
            KpiViewModel("internal", "Productos internos", str(counts["internal"]), "neutral"),
            KpiViewModel("incomplete", "Incompletos", str(counts["incomplete"]),
                         "danger" if counts["incomplete"] else "success"),
            KpiViewModel("recipes_unapproved", "Recetas sin aprobar",
                         str(counts["recipes_unapproved"]),
                         "warning" if counts["recipes_unapproved"] else "success"),
            KpiViewModel("yield_pending", "Rendimientos pendientes",
                         str(counts["yield_pending"]),
                         "warning" if counts["yield_pending"] else "success"),
        ]

    # ── catálogo (§43) ────────────────────────────────────────────────────
    def catalog(self, *, query: str | None = None, product_type: str | None = None
                ) -> TableViewModel:
        rows = self._read_factory().list_catalog(query=query, product_type=product_type)
        return catalog_table(rows)

    # ── alertas (§35) ─────────────────────────────────────────────────────
    def recent_alerts(self) -> TableViewModel:
        return alerts_table(self._read_factory().list_recent_alerts())
