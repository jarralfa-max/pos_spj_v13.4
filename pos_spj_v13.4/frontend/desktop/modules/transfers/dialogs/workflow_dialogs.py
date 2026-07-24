"""Standard workflow dialogs; callers submit captured values to application UseCases."""
from frontend.desktop.components.barcode_input import BarcodeInput
from frontend.desktop.components.decimal_input import DecimalInput
from frontend.desktop.components.dialogs import FormDialog
from frontend.desktop.components.search_input import SearchInput


class TransferRequestDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Nueva solicitud de transferencia")
        self.origin = SearchInput(self, placeholder="Buscar origen…")
        self.destination = SearchInput(self, placeholder="Buscar destino…")
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.form.addRow("Origen", self.origin)
        self.form.addRow("Destino", self.destination)
        self.form.addRow("Cantidad", self.quantity)
        self.form.addRow("Peso", self.weight)
        self.add_button_box(ok_text="Crear solicitud")


class TransferApprovalDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Aprobar transferencia")
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.form.addRow("Cantidad aprobada", self.quantity)
        self.form.addRow("Peso aprobado", self.weight)
        self.add_button_box(ok_text="Confirmar aprobación")


class PickingDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Captura de picking")
        self.location = BarcodeInput(self, placeholder="Escanea ubicación")
        self.product = BarcodeInput(self, placeholder="Escanea producto")
        self.lot = BarcodeInput(self, placeholder="Escanea lote")
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.form.addRow("Ubicación", self.location)
        self.form.addRow("Producto", self.product)
        self.form.addRow("Lote", self.lot)
        self.form.addRow("Peso", self.weight)
        self.add_button_box(ok_text="Confirmar picking")


class TransferReceiptDialog(FormDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent, title="Recibir transferencia")
        self.qr = BarcodeInput(self, placeholder="Escanea QR de transferencia o embarque")
        self.product = BarcodeInput(self, placeholder="Escanea producto")
        self.quantity = DecimalInput(self, precision=3, minimum="0")
        self.weight = DecimalInput(self, precision=3, minimum="0", suffix="kg")
        self.temperature = DecimalInput(self, precision=2, nullable=True, suffix="°C")
        self.form.addRow("Transferencia / QR", self.qr)
        self.form.addRow("Producto", self.product)
        self.form.addRow("Cantidad", self.quantity)
        self.form.addRow("Peso", self.weight)
        self.form.addRow("Temperatura", self.temperature)
        self.add_button_box(ok_text="Confirmar recepción")


BlindReceiptDialog = TransferReceiptDialog
MaterialAllocationDialog = PickingDialog
PartialDispatchDialog = PickingDialog
DispatchDialog = PickingDialog
DifferenceResolutionDialog = TransferApprovalDialog
ReturnToOriginDialog = TransferRequestDialog
CancelTransferDialog = TransferApprovalDialog
ReverseTransferDialog = TransferApprovalDialog
