"""Application command DTOs for canonical use cases."""

from backend.application.commands.base_command import BaseCommand
from backend.application.commands.cash_register_commands import (
    CloseCashShiftCommand,
    GenerateZCutCommand,
    OpenCashShiftCommand,
    RegisterCashMovementCommand,
)
from backend.application.commands.delivery_commands import CreateDeliveryOrderCommand
from backend.application.commands.product_commands import CreateProductCommand, UpdateProductCommand
from backend.application.commands.production_commands import ExecuteMeatProductionCommand
from backend.application.commands.purchase_planning_commands import GeneratePurchasePlanCommand
from backend.application.commands.quote_commands import ConvertQuoteToSaleCommand
from backend.application.commands.sales_commands import CreateSaleCommand
from backend.application.commands.transfer_commands import DispatchTransferCommand, ReceiveTransferCommand
from backend.application.commands.waste_commands import RegisterWasteCommand

__all__ = [
    "BaseCommand",
    "CloseCashShiftCommand",
    "GenerateZCutCommand",
    "OpenCashShiftCommand",
    "RegisterCashMovementCommand",
    "CreateDeliveryOrderCommand",
    "CreateProductCommand",
    "UpdateProductCommand",
    "ExecuteMeatProductionCommand",
    "GeneratePurchasePlanCommand",
    "ConvertQuoteToSaleCommand",
    "CreateSaleCommand",
    "DispatchTransferCommand",
    "ReceiveTransferCommand",
    "RegisterWasteCommand",
]
