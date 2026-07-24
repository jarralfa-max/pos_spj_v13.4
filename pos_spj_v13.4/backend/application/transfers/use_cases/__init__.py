"""Use cases for the canonical Transfers application layer."""

from .transfer_dispatch_use_cases import DispatchTransferShipmentUseCase
from .transfer_receipt_use_cases import ConfirmTransferReceiptUseCase, TransferReceiptQrValidator
from .blind_receipt_use_cases import (
    CaptureBlindReceiptUseCase,
    ConfirmBlindReceiptUseCase,
    StartBlindReceiptUseCase,
)
from .transfer_difference_use_cases import (
    DetectTransferDifferencesUseCase,
    ResolveTransferDifferenceUseCase,
    ReviewTransferDifferenceUseCase,
)
from .transfer_return_use_cases import (
    ApproveTransferReturnUseCase,
    CreateTransferReturnUseCase,
    DispatchTransferReturnUseCase,
    ReceiveTransferReturnUseCase,
    TransferReturnNumberGenerator,
)
from .transfer_suggestion_use_cases import (
    ForecastTransferSuggestionRequestedHandler,
    GenerateTransferSuggestionsUseCase,
    TransferSuggestionSettingsQueryService,
    TransferSuggestionSupplyQueryService,
)
from .transfer_packaging_use_cases import CreateTransferPackageUseCase, TransferPackageLabelGateway
from .transfer_picking_use_cases import (
    BuildTransferPickingListUseCase,
    ConfirmTransferPickingUseCase,
    StartTransferPickingUseCase,
    TransferBarcodeValidator,
)
from .transfer_reservation_use_cases import ReserveTransferInventoryUseCase, TransferLotAvailabilityReadPort
from .transfer_request_use_cases import (
    ApproveTransferRequestUseCase,
    CreateTransferRequestUseCase,
    EditTransferRequestUseCase,
    RejectTransferRequestUseCase,
    SubmitTransferRequestUseCase,
    TransferRequestNumberGenerator,
)
