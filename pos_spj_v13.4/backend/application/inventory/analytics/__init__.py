"""Inventory BI / analytics (read-side, §55). INV-24."""

from backend.application.inventory.analytics.inventory_analytics_service import (
    InventoryAnalyticsService,
    InventoryKpiDTO,
)

__all__ = ["InventoryAnalyticsService", "InventoryKpiDTO"]
