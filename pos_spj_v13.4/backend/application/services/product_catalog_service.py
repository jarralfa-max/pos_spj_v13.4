"""Canonical application service for product catalog mutations."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4
import logging

from backend.application.commands.product_commands import CreateProductCommand, UpdateProductCommand
from backend.application.dto.use_case_result import UseCaseResult
from backend.domain.services.product_type_policy import ProductTypePolicy
from backend.shared.events.event_bus import EventBus, InMemoryEventBus
from backend.shared.events.event_contracts import create_domain_event
from backend.shared.events.event_names import EventName

logger = logging.getLogger(__name__)


class ProductRepositoryProtocol(Protocol):
    def get_by_id(self, product_id: int | str) -> dict[str, Any] | None: ...
    def sku_exists(self, sku: str, *, exclude_product_id: int | str | None = None) -> dict[str, Any] | None: ...
    def active_name_duplicate(self, name: str, *, exclude_product_id: int | str | None = None) -> dict[str, Any] | None: ...
    def has_active_recipe(self, product_id: int | str) -> bool: ...
    def create(self, product_data: dict[str, Any]) -> str: ...
    def update(self, product_id: int | str, product_data: dict[str, Any]) -> str: ...
    def save_changes(self) -> None: ...
    def rollback_changes(self) -> None: ...


class ProductPricingService:
    """Normalizes base product price and cost numbers."""

    @staticmethod
    def normalize_price(value: float | int | None) -> float:
        return round(max(float(value or 0.0), 0.0), 2)

    @classmethod
    def normalize_money_fields(cls, command: CreateProductCommand) -> dict[str, float]:
        return {
            "sale_price": cls.normalize_price(command.sale_price),
            "purchase_price": cls.normalize_price(command.purchase_price),
            "minimum_sale_price": cls.normalize_price(command.minimum_sale_price),
        }


class ProductImageService:
    """Keeps catalog image path handling behind the application boundary."""

    @staticmethod
    def normalize_path(path: str | None) -> str | None:
        value = (path or "").strip()
        return value or None


class ProductBarcodeService:
    """Keeps barcode/SKU normalization behind the application boundary."""

    @staticmethod
    def normalize_barcode(value: str | None) -> str:
        return (value or "").strip()

    @staticmethod
    def normalize_sku(value: str | None) -> str:
        clean = (value or "").strip()
        return clean or f"P-{uuid4().hex[:8].upper()}"


class ProductRecipeConfigService:
    """Reports recipe status without changing recipe data."""

    def __init__(self, repository: ProductRepositoryProtocol) -> None:
        self._repository = repository

    def recipe_pending_for(self, *, product_id: int | str, product_type: str) -> bool:
        rules = ProductTypePolicy.rules_for(product_type)
        return rules.allows_recipe and not self._repository.has_active_recipe(product_id)


class ProductCatalogService:
    """Coordinates the single canonical product catalog mutation route."""

    def __init__(
        self,
        *,
        repository: ProductRepositoryProtocol,
        event_bus: EventBus | None = None,
        pricing_service: ProductPricingService | None = None,
        image_service: ProductImageService | None = None,
        barcode_service: ProductBarcodeService | None = None,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus or InMemoryEventBus()
        self._pricing = pricing_service or ProductPricingService()
        self._image = image_service or ProductImageService()
        self._barcode = barcode_service or ProductBarcodeService()
        self._recipes = ProductRecipeConfigService(repository)

    def create(self, command: CreateProductCommand) -> UseCaseResult:
        command.validate_context()
        product_data_or_error = self._build_product_data(command)
        if isinstance(product_data_or_error, UseCaseResult):
            return product_data_or_error
        product_data = product_data_or_error

        duplicate_result = self._validate_duplicates(command, product_data, exclude_product_id=None)
        if duplicate_result is not None:
            return duplicate_result

        try:
            product_id = self._repository.create(product_data)
            self._repository.save_changes()
        except Exception:
            self._rollback(command.operation_id)
            return UseCaseResult(False, command.operation_id, message="PRODUCT_CREATE_FAILED")

        return self._success(command, product_id, EventName.PRODUCT_CREATED, product_data)

    def update(self, command: UpdateProductCommand) -> UseCaseResult:
        command.validate_context()
        if not command.product_id:
            return UseCaseResult(False, command.operation_id, message="PRODUCT_ID_REQUIRED")
        if self._repository.get_by_id(command.product_id) is None:
            return UseCaseResult(False, command.operation_id, message="PRODUCT_NOT_FOUND")

        product_data_or_error = self._build_product_data(command)
        if isinstance(product_data_or_error, UseCaseResult):
            return product_data_or_error
        product_data = product_data_or_error

        duplicate_result = self._validate_duplicates(command, product_data, exclude_product_id=command.product_id)
        if duplicate_result is not None:
            return duplicate_result

        try:
            product_id = self._repository.update(command.product_id, product_data)
            self._repository.save_changes()
        except Exception:
            self._rollback(command.operation_id)
            return UseCaseResult(False, command.operation_id, message="PRODUCT_UPDATE_FAILED")

        return self._success(command, product_id, EventName.PRODUCT_UPDATED, product_data)

    def _build_product_data(self, command: CreateProductCommand) -> dict[str, Any] | UseCaseResult:
        name = command.name.strip()
        if not name:
            return UseCaseResult(False, command.operation_id, message="PRODUCT_NAME_REQUIRED")
        try:
            rules = ProductTypePolicy.rules_for(command.product_type)
        except ValueError:
            return UseCaseResult(False, command.operation_id, message="PRODUCT_TYPE_UNSUPPORTED")

        prices = self._pricing.normalize_money_fields(command)
        minimum_stock = max(float(command.minimum_stock or 0.0), 0.0)
        unit = (command.unit or command.sale_unit or command.purchase_unit or "").strip() or "pza"
        return {
            "name": name,
            "sku": self._barcode.normalize_sku(command.sku),
            "barcode": self._barcode.normalize_barcode(command.barcode),
            "category": command.category.strip(),
            "unit": unit,
            "sale_unit": (command.sale_unit or unit).strip(),
            "purchase_unit": (command.purchase_unit or unit).strip(),
            "minimum_stock": minimum_stock,
            "product_type": rules.code,
            "is_composite": 1 if rules.is_composite else 0,
            "is_byproduct": 1 if rules.is_byproduct else 0,
            "active": bool(command.active),
            "image_path": self._image.normalize_path(command.image_path),
            **prices,
        }

    def _validate_duplicates(
        self,
        command: CreateProductCommand,
        product_data: dict[str, Any],
        *,
        exclude_product_id: int | str | None,
    ) -> UseCaseResult | None:
        sku_duplicate = self._repository.sku_exists(product_data["sku"], exclude_product_id=exclude_product_id)
        if sku_duplicate is not None:
            return UseCaseResult(False, command.operation_id, message="PRODUCT_SKU_DUPLICATE", data=sku_duplicate)
        name_duplicate = self._repository.active_name_duplicate(product_data["name"], exclude_product_id=exclude_product_id)
        if name_duplicate is not None and not command.allow_duplicate_name:
            return UseCaseResult(False, command.operation_id, message="PRODUCT_NAME_DUPLICATE_ACTIVE", data=name_duplicate)
        return None

    def _success(
        self,
        command: CreateProductCommand,
        product_id: int | str,
        event_name: EventName,
        product_data: dict[str, Any],
    ) -> UseCaseResult:
        recipe_pending = self._recipes.recipe_pending_for(product_id=product_id, product_type=product_data["product_type"])
        event = create_domain_event(
            event_name=event_name,
            operation_id=command.operation_id,
            entity_id=str(product_id),
            branch_id=str(command.branch_id),
            user_id=command.user_id,
            user_name=command.user_name,
            source_module="products",
            payload={
                "product_id": str(product_id),
                "name": product_data["name"],
                "sku": product_data["sku"],
                "product_type": product_data["product_type"],
                "sale_price": product_data["sale_price"],
                "purchase_price": product_data["purchase_price"],
                "minimum_stock": product_data["minimum_stock"],
                "recipe_pending": recipe_pending,
            },
        )
        published_events: tuple[Any, ...] = ()
        side_effect_errors: list[str] = []
        try:
            self._event_bus.publish(event)
            published_events = (event,)
        except Exception:
            side_effect_errors.append("PRODUCT_EVENT_PUBLISH_FAILED")
            logger.exception("[PRODUCTS] event publish failed operation_id=%s product_id=%s", command.operation_id, product_id)
        message = "PRODUCT_CREATED" if event_name is EventName.PRODUCT_CREATED else "PRODUCT_UPDATED"
        return UseCaseResult(
            True,
            command.operation_id,
            entity_id=str(product_id),
            message=message,
            data={"product_id": str(product_id), "recipe_pending": recipe_pending, "side_effect_errors": tuple(side_effect_errors)},
            events=published_events,
        )

    def _rollback(self, operation_id: str) -> None:
        try:
            self._repository.rollback_changes()
        except Exception:
            logger.exception("[PRODUCTS] rollback failed operation_id=%s", operation_id)
