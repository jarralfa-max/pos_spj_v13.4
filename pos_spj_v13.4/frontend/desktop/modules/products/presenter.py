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
                 attributes_write_factory=None, variants_read_factory=None,
                 variants_write_factory=None, images_read_factory=None,
                 images_write_factory=None, recipes_read_factory=None,
                 recipes_write_factory=None, yields_read_factory=None,
                 yields_write_factory=None, cutting_read_factory=None,
                 cutting_write_factory=None, bundles_read_factory=None,
                 bundles_write_factory=None, import_read_factory=None,
                 import_write_factory=None, species_read_factory=None,
                 branch_read_factory=None, branch_write_factory=None,
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
        self._variants_read = variants_read_factory
        self._variants_write = variants_write_factory
        self._images_read = images_read_factory
        self._images_write = images_write_factory
        self._recipes_read = recipes_read_factory
        self._recipes_write = recipes_write_factory
        self._yields_read = yields_read_factory
        self._yields_write = yields_write_factory
        self._cutting_read = cutting_read_factory
        self._cutting_write = cutting_write_factory
        self._bundles_read = bundles_read_factory
        self._bundles_write = bundles_write_factory
        self._import_read = import_read_factory
        self._import_write = import_write_factory
        self._species_read = species_read_factory
        self._branch_read = branch_read_factory
        self._branch_write = branch_write_factory
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
                res = ucs["edit"].execute(UpdateCategoryCommand(
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
                res = ucs["edit"].execute(UpdateBrandCommand(
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
                res = ucs["edit"].execute(UpdateAttributeCommand(
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

    # ── variantes (P1-03) ──────────────────────────────────────────────────
    @property
    def can_generate_variants(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._variants_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.VARIANTS_GENERATE))

    def variant_axes_catalog(self) -> list[dict]:
        """Atributos LISTA con sus opciones, para elegir los ejes de variación."""
        if self._attributes_read is None:
            return []
        try:
            return self._attributes_read().attributes_with_options(active_only=True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron cargar ejes de variante")
            return []

    def list_variants(self, parent_product_id: str) -> list[dict]:
        if self._variants_read is None:
            return []
        try:
            return self._variants_read().list_variants(parent_product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar variantes")
            return []

    def generate_variants(self, *, parent_product_id: str,
                          axes: dict) -> tuple[bool, str]:
        if self._variants_write is None:
            return False, "Sin permisos de generación de variantes"
        from backend.application.products.commands.product_variant_commands import (
            GenerateVariantsCommand,
        )
        from backend.shared.ids import new_uuid
        uc = self._variants_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            res = uc.execute(GenerateVariantsCommand(
                operation_id=new_uuid(), parent_product_id=parent_product_id,
                axes=axes, user_id=user_id))
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Generación de variantes falló")
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── imágenes (P1) ──────────────────────────────────────────────────────
    @property
    def can_manage_images(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._images_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.IMAGES_MANAGE))

    def list_images(self, product_id: str) -> list[dict]:
        if self._images_read is None:
            return []
        try:
            return self._images_read().list_images(product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar imágenes")
            return []

    def add_image(self, *, product_id: str, uri: str, alt_text: str | None = None,
                  make_primary: bool = False) -> tuple[bool, str]:
        return self._run_image("add", product_id=product_id, uri=uri,
                               alt_text=alt_text, make_primary=make_primary)

    def set_primary_image(self, image_id: str) -> tuple[bool, str]:
        return self._run_image("set_primary", image_id=image_id)

    def remove_image(self, image_id: str) -> tuple[bool, str]:
        return self._run_image("remove", image_id=image_id)

    def _run_image(self, action: str, **kw) -> tuple[bool, str]:
        if self._images_write is None:
            return False, "Sin permisos de gestión de imágenes"
        from backend.application.products.commands.product_image_commands import (
            AddProductImageCommand,
            RemoveProductImageCommand,
            SetPrimaryImageCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._images_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "add":
                cmd = AddProductImageCommand(
                    operation_id=new_uuid(), product_id=kw["product_id"],
                    uri=kw["uri"], alt_text=kw.get("alt_text"),
                    make_primary=bool(kw.get("make_primary")), user_id=user_id)
            elif action == "set_primary":
                cmd = SetPrimaryImageCommand(
                    operation_id=new_uuid(), image_id=kw["image_id"], user_id=user_id)
            else:
                cmd = RemoveProductImageCommand(
                    operation_id=new_uuid(), image_id=kw["image_id"], user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de imagen %s falló", action)
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── recetas (capa de aplicación) ───────────────────────────────────────
    @property
    def can_manage_recipes(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._recipes_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.RECIPE_CREATE)
                    or self._has_permission(ProductPermissions.RECIPE_EDIT))

    def list_recipes(self, product_id: str) -> list[dict]:
        if self._recipes_read is None:
            return []
        try:
            return self._recipes_read().list_recipes(product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar recetas")
            return []

    def list_recipe_versions(self, recipe_id: str) -> list[dict]:
        if self._recipes_read is None:
            return []
        try:
            return self._recipes_read().list_versions(recipe_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar versiones de receta")
            return []

    def recipe_version_detail(self, version_id: str) -> dict | None:
        if self._recipes_read is None:
            return None
        try:
            return self._recipes_read().version_detail(version_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener el detalle de la versión")
            return None

    def create_recipe(self, *, product_id: str, recipe_type: str, name: str,
                       components: list[dict], outputs: list[dict] | None = None
                       ) -> tuple[bool, str]:
        return self._run_recipe(
            "create", product_id=product_id, recipe_type=recipe_type, name=name,
            components=components, outputs=outputs or [])

    def update_draft_version(self, *, version_id: str, components: list[dict],
                             outputs: list[dict] | None = None) -> tuple[bool, str]:
        return self._run_recipe("edit", version_id=version_id,
                                components=components, outputs=outputs or [])

    def submit_recipe_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_recipe("submit", version_id=version_id)

    def approve_recipe_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_recipe("approve", version_id=version_id)

    def activate_recipe_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_recipe("activate", version_id=version_id)

    def _run_recipe(self, action: str, **kw) -> tuple[bool, str]:
        if self._recipes_write is None:
            return False, "Sin permisos de gestión de recetas"
        from backend.application.products.commands.product_recipe_commands import (
            CreateRecipeCommand,
            RecipeVersionTransitionCommand,
            UpdateDraftVersionCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._recipes_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "create":
                cmd = CreateRecipeCommand(
                    operation_id=new_uuid(), product_id=kw["product_id"],
                    recipe_type=kw["recipe_type"], name=kw["name"],
                    components=kw["components"], outputs=kw["outputs"],
                    user_id=user_id)
            elif action == "edit":
                cmd = UpdateDraftVersionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    components=kw["components"], outputs=kw["outputs"],
                    user_id=user_id)
            else:
                cmd = RecipeVersionTransitionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de receta %s falló", action)
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── rendimientos (yields) ──────────────────────────────────────────────
    @property
    def can_manage_yields(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._yields_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.YIELD_CREATE)
                    or self._has_permission(ProductPermissions.YIELD_EDIT))

    def list_yield_profiles(self, input_product_id: str) -> list[dict]:
        if self._yields_read is None:
            return []
        try:
            return self._yields_read().list_profiles(input_product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar rendimientos")
            return []

    def list_yield_versions(self, profile_id: str) -> list[dict]:
        if self._yields_read is None:
            return []
        try:
            return self._yields_read().list_versions(profile_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar versiones de rendimiento")
            return []

    def yield_version_detail(self, version_id: str) -> dict | None:
        if self._yields_read is None:
            return None
        try:
            return self._yields_read().version_detail(version_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener el detalle de la versión")
            return None

    def create_yield_profile(self, *, input_product_id: str, name: str,
                             tolerance_pct: str, outputs: list[dict]
                             ) -> tuple[bool, str]:
        return self._run_yield("create", input_product_id=input_product_id, name=name,
                               tolerance_pct=tolerance_pct, outputs=outputs)

    def update_yield_version(self, *, version_id: str, tolerance_pct: str,
                             outputs: list[dict]) -> tuple[bool, str]:
        return self._run_yield("edit", version_id=version_id,
                               tolerance_pct=tolerance_pct, outputs=outputs)

    def submit_yield_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_yield("submit", version_id=version_id)

    def approve_yield_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_yield("approve", version_id=version_id)

    def activate_yield_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_yield("activate", version_id=version_id)

    def _run_yield(self, action: str, **kw) -> tuple[bool, str]:
        if self._yields_write is None:
            return False, "Sin permisos de gestión de rendimientos"
        from backend.application.products.commands.product_yield_commands import (
            CreateYieldProfileCommand,
            UpdateYieldVersionCommand,
            YieldVersionTransitionCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._yields_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "create":
                cmd = CreateYieldProfileCommand(
                    operation_id=new_uuid(), input_product_id=kw["input_product_id"],
                    name=kw["name"], tolerance_pct=kw["tolerance_pct"],
                    outputs=kw["outputs"], user_id=user_id)
            elif action == "edit":
                cmd = UpdateYieldVersionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    tolerance_pct=kw["tolerance_pct"], outputs=kw["outputs"],
                    user_id=user_id)
            else:
                cmd = YieldVersionTransitionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de rendimiento %s falló", action)
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── esquemas de despiece (cutting) ─────────────────────────────────────
    @property
    def can_manage_cutting(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._cutting_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.CUTTING_SCHEME_MANAGE))

    def list_cutting_schemes(self, input_product_id: str) -> list[dict]:
        if self._cutting_read is None:
            return []
        try:
            return self._cutting_read().list_schemes(input_product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar esquemas de despiece")
            return []

    def list_cutting_versions(self, scheme_id: str) -> list[dict]:
        if self._cutting_read is None:
            return []
        try:
            return self._cutting_read().list_versions(scheme_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar versiones de despiece")
            return []

    def cutting_version_detail(self, version_id: str) -> dict | None:
        if self._cutting_read is None:
            return None
        try:
            return self._cutting_read().version_detail(version_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener el detalle de la versión")
            return None

    def create_cutting_scheme(self, *, input_product_id: str, species_id: str,
                              name: str, cut_level: str, outputs: list[dict]
                              ) -> tuple[bool, str]:
        return self._run_cutting("create", input_product_id=input_product_id,
                                 species_id=species_id, name=name,
                                 cut_level=cut_level, outputs=outputs)

    def update_cutting_version(self, *, version_id: str,
                               outputs: list[dict]) -> tuple[bool, str]:
        return self._run_cutting("edit", version_id=version_id, outputs=outputs)

    def submit_cutting_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_cutting("submit", version_id=version_id)

    def approve_cutting_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_cutting("approve", version_id=version_id)

    def activate_cutting_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_cutting("activate", version_id=version_id)

    def _run_cutting(self, action: str, **kw) -> tuple[bool, str]:
        if self._cutting_write is None:
            return False, "Sin permisos de gestión de despiece"
        from backend.application.products.commands.product_cutting_commands import (
            CreateCuttingSchemeCommand,
            CuttingVersionTransitionCommand,
            UpdateCuttingVersionCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._cutting_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "create":
                cmd = CreateCuttingSchemeCommand(
                    operation_id=new_uuid(), input_product_id=kw["input_product_id"],
                    species_id=kw["species_id"], name=kw["name"],
                    cut_level=kw["cut_level"], outputs=kw["outputs"], user_id=user_id)
            elif action == "edit":
                cmd = UpdateCuttingVersionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    outputs=kw["outputs"], user_id=user_id)
            else:
                cmd = CuttingVersionTransitionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de despiece %s falló", action)
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── combos / kits (§28) ─────────────────────────────────────────────────
    @property
    def can_manage_bundles(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._bundles_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.BUNDLES_MANAGE))

    def list_bundles(self, product_id: str) -> list[dict]:
        if self._bundles_read is None:
            return []
        try:
            return self._bundles_read().list_bundles(product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar combos")
            return []

    def list_bundle_versions(self, bundle_id: str) -> list[dict]:
        if self._bundles_read is None:
            return []
        try:
            return self._bundles_read().list_versions(bundle_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar versiones de combo")
            return []

    def bundle_version_detail(self, version_id: str) -> dict | None:
        if self._bundles_read is None:
            return None
        try:
            return self._bundles_read().version_detail(version_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo obtener el detalle de la versión")
            return None

    def create_bundle(self, *, product_id: str, bundle_type: str, name: str,
                      components: list[dict]) -> tuple[bool, str]:
        return self._run_bundle("create", product_id=product_id,
                                bundle_type=bundle_type, name=name,
                                components=components)

    def update_bundle_version(self, *, version_id: str,
                              components: list[dict]) -> tuple[bool, str]:
        return self._run_bundle("edit", version_id=version_id,
                                components=components)

    def submit_bundle_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_bundle("submit", version_id=version_id)

    def approve_bundle_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_bundle("approve", version_id=version_id)

    def activate_bundle_version(self, version_id: str) -> tuple[bool, str]:
        return self._run_bundle("activate", version_id=version_id)

    def _run_bundle(self, action: str, **kw) -> tuple[bool, str]:
        if self._bundles_write is None:
            return False, "Sin permisos de gestión de combos"
        from backend.application.products.commands.product_bundle_commands import (
            BundleVersionTransitionCommand,
            CreateBundleCommand,
            UpdateBundleVersionCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._bundles_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "create":
                cmd = CreateBundleCommand(
                    operation_id=new_uuid(), product_id=kw["product_id"],
                    bundle_type=kw["bundle_type"], name=kw["name"],
                    components=kw["components"], user_id=user_id)
            elif action == "edit":
                cmd = UpdateBundleVersionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    components=kw["components"], user_id=user_id)
            else:
                cmd = BundleVersionTransitionCommand(
                    operation_id=new_uuid(), version_id=kw["version_id"],
                    user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de combo %s falló", action)
            return False, f"Error: {exc}"
        return res.success, res.message

    # ── importación CSV/XLSX ────────────────────────────────────────────────
    @property
    def can_import(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._import_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.IMPORT_EXECUTE))

    @property
    def can_approve_import(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._has_permission is None:
            return self._import_write is not None
        return bool(self._has_permission(ProductPermissions.IMPORT_APPROVE))

    def list_import_jobs(self) -> list[dict]:
        if self._import_read is None:
            return []
        try:
            return self._import_read().list_jobs()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar importaciones")
            return []

    def import_preview(self, job_id: str) -> list[dict]:
        if self._import_read is None:
            return []
        try:
            return self._import_read().preview_rows(job_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudo cargar la vista previa")
            return []

    def create_import_batch(self, *, filename: str,
                            data: bytes) -> tuple[bool, str, str | None]:
        return self._run_import("create", filename=filename, data=data)

    def approve_import_batch(self, job_id: str) -> tuple[bool, str, str | None]:
        return self._run_import("approve", job_id=job_id)

    def execute_import_batch(self, job_id: str) -> tuple[bool, str, str | None]:
        return self._run_import("execute", job_id=job_id)

    def _run_import(self, action: str, **kw) -> tuple[bool, str, str | None]:
        if self._import_write is None:
            return False, "Sin permisos de importación", None
        from backend.application.products.commands.product_import_commands import (
            CreateImportBatchCommand,
            ImportBatchActionCommand,
        )
        from backend.shared.ids import new_uuid
        ucs = self._import_write()
        user_id = getattr(self._session, "user_id", None)
        try:
            if action == "create":
                cmd = CreateImportBatchCommand(
                    operation_id=new_uuid(), filename=kw["filename"],
                    data=kw["data"], user_id=user_id)
            else:
                cmd = ImportBatchActionCommand(
                    operation_id=new_uuid(), job_id=kw["job_id"], user_id=user_id)
            res = ucs[action].execute(cmd)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Acción de importación %s falló", action)
            return False, f"Error: {exc}", None
        return res.success, res.message, res.job_id

    def list_units(self) -> list[dict]:
        """Unidades del catálogo para el selector del formulario (P0-03)."""
        if self._units_factory is None:
            return []
        try:
            return self._units_factory().list_units()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar unidades")
            return []

    def list_species(self) -> list[dict]:
        """Especies del catálogo para el selector cárnico del formulario (§5.2).

        Devuelve ``[{id, code, label}]`` (guarda `species.id`, nunca texto libre
        ni UUID escrito a mano)."""
        if self._species_read is None:
            return []
        try:
            return self._species_read().options(active_only=True)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar especies")
            return []

    # ── asignación sucursal / canal (§10) ─────────────────────────────────
    @property
    def can_manage_branch_assignment(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._branch_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.BRANCH_ASSIGNMENT_MANAGE))

    @property
    def can_manage_assortment(self) -> bool:
        from backend.application.products.permissions import ProductPermissions
        if self._branch_write is None:
            return False
        if self._has_permission is None:
            return True
        return bool(self._has_permission(ProductPermissions.ASSORTMENT_MANAGE))

    def search_products_for_assignment(self, query: str | None = None) -> list[dict]:
        """Productos para el selector de la página de sucursales/canales."""
        try:
            return self._read_factory().list_catalog(query=query)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron buscar productos")
            return []

    def branch_assignments(self, product_id: str) -> list[dict]:
        if self._branch_read is None:
            return []
        try:
            return self._branch_read().branch_assignments(product_id)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar sucursales")
            return []

    def list_channels(self) -> list[dict]:
        if self._branch_read is None:
            return []
        try:
            return self._branch_read().channels()
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar canales")
            return []

    def assortments(self, product_id: str, *, channel: str | None = None) -> list[dict]:
        if self._branch_read is None:
            return []
        try:
            return self._branch_read().assortments(product_id, channel=channel)
        except Exception:  # pragma: no cover - defensive
            logger.exception("No se pudieron listar surtidos")
            return []

    def set_branch_enabled(self, *, product_id: str, branch_id: str,
                           enabled: bool) -> tuple[bool, str]:
        if self._branch_write is None:
            return False, "Sin permisos de asignación por sucursal"
        user_id = getattr(self._session, "user_id", None)
        try:
            res = self._branch_write()["branch"].execute(
                product_id=product_id, branch_id=branch_id, enabled=enabled,
                user_id=user_id)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Asignación por sucursal falló")
            return False, f"Error: {exc}"
        return res.success, res.message

    def create_assortment(self, *, name: str, channel: str,
                          branch_id: str | None = None) -> tuple[bool, str]:
        if self._branch_write is None:
            return False, "Sin permisos de surtido"
        user_id = getattr(self._session, "user_id", None)
        try:
            res = self._branch_write()["create_assortment"].execute(
                name=name, channel=channel, branch_id=branch_id, user_id=user_id)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Creación de surtido falló")
            return False, f"Error: {exc}"
        return res.success, res.message

    def set_assortment_product(self, *, assortment_id: str, product_id: str,
                               enabled: bool) -> tuple[bool, str]:
        if self._branch_write is None:
            return False, "Sin permisos de surtido"
        user_id = getattr(self._session, "user_id", None)
        try:
            res = self._branch_write()["set_assortment_product"].execute(
                assortment_id=assortment_id, product_id=product_id, enabled=enabled,
                user_id=user_id)
        except Exception as exc:  # noqa: BLE001 — mostrado en la UI
            logger.exception("Asignación a surtido falló")
            return False, f"Error: {exc}"
        return res.success, res.message

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
