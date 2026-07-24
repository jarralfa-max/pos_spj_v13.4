"""Infrastructure contract marker; concrete desktop/spool adapters implement the port."""
from backend.application.transfers.printing import TransfersPrintGateway

__all__ = ["TransfersPrintGateway"]
