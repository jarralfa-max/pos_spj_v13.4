"""Canonical enums for the Device Management bounded context — SET-7.
See docs/refactor/settings_refactor_execution_plan.md and the master
prompt §18-20.
"""

from __future__ import annotations

from enum import Enum


class DeviceType(str, Enum):
    """What kind of hardware a `Device`/`DeviceProfile` is. See §18."""

    THERMAL_PRINTER = "THERMAL_PRINTER"
    LABEL_PRINTER = "LABEL_PRINTER"
    DOCUMENT_PRINTER = "DOCUMENT_PRINTER"
    SCALE = "SCALE"
    BARCODE_SCANNER = "BARCODE_SCANNER"
    QR_SCANNER = "QR_SCANNER"
    CASH_DRAWER = "CASH_DRAWER"
    PAYMENT_TERMINAL = "PAYMENT_TERMINAL"
    CUSTOMER_DISPLAY = "CUSTOMER_DISPLAY"
    TEMPERATURE_SENSOR = "TEMPERATURE_SENSOR"
    CARD_PRINTER = "CARD_PRINTER"
    MOBILE_DEVICE = "MOBILE_DEVICE"
    OTHER = "OTHER"


class ConnectionType(str, Enum):
    """How a device is reached. See §18."""

    USB = "USB"
    SERIAL = "SERIAL"
    BLUETOOTH = "BLUETOOTH"
    NETWORK = "NETWORK"
    HTTP = "HTTP"
    WEBSOCKET = "WEBSOCKET"
    SYSTEM = "SYSTEM"
    VIRTUAL = "VIRTUAL"


# Connection types that address a remote endpoint (host/port) rather than
# a local bus — used to decide when a `NetworkEndpoint` is required.
NETWORK_ADDRESSED_CONNECTION_TYPES = frozenset({
    ConnectionType.NETWORK, ConnectionType.HTTP, ConnectionType.WEBSOCKET,
})


class DeviceStatus(str, Enum):
    """Lifecycle of a `Device`. Deliberately the same five values as
    `backend/domain/settings/enums.py::WorkstationStatus` and Cash
    Register's `cash_registers`/`pos_terminals` — one shared hardware/
    station lifecycle vocabulary — defined independently here (not
    imported) to keep `device_management` free of a dependency on the
    `settings` bounded context."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    MAINTENANCE = "MAINTENANCE"
    BLOCKED = "BLOCKED"
    RETIRED = "RETIRED"


class AssignmentRole(str, Enum):
    """What role a device plays at a workstation. See §20 — a
    workstation may hold at most one *active* device per role (enforced
    by the schema's partial unique index, not here)."""

    PRIMARY_RECEIPT_PRINTER = "PRIMARY_RECEIPT_PRINTER"
    SECONDARY_RECEIPT_PRINTER = "SECONDARY_RECEIPT_PRINTER"
    LABEL_PRINTER = "LABEL_PRINTER"
    KITCHEN_PRINTER = "KITCHEN_PRINTER"
    PRODUCTION_PRINTER = "PRODUCTION_PRINTER"
    TRANSFER_PRINTER = "TRANSFER_PRINTER"
    SCALE = "SCALE"
    SCANNER = "SCANNER"
    CASH_DRAWER = "CASH_DRAWER"
    PAYMENT_TERMINAL = "PAYMENT_TERMINAL"
    CUSTOMER_DISPLAY = "CUSTOMER_DISPLAY"


# Which DeviceType(s) each AssignmentRole may legally point at (§20).
ROLE_COMPATIBLE_DEVICE_TYPES: dict[AssignmentRole, frozenset[DeviceType]] = {
    AssignmentRole.PRIMARY_RECEIPT_PRINTER: frozenset({DeviceType.THERMAL_PRINTER, DeviceType.DOCUMENT_PRINTER}),
    AssignmentRole.SECONDARY_RECEIPT_PRINTER: frozenset({DeviceType.THERMAL_PRINTER, DeviceType.DOCUMENT_PRINTER}),
    AssignmentRole.KITCHEN_PRINTER: frozenset({DeviceType.THERMAL_PRINTER, DeviceType.DOCUMENT_PRINTER}),
    AssignmentRole.PRODUCTION_PRINTER: frozenset({DeviceType.THERMAL_PRINTER, DeviceType.DOCUMENT_PRINTER}),
    AssignmentRole.TRANSFER_PRINTER: frozenset({DeviceType.THERMAL_PRINTER, DeviceType.DOCUMENT_PRINTER}),
    AssignmentRole.LABEL_PRINTER: frozenset({DeviceType.LABEL_PRINTER}),
    AssignmentRole.SCALE: frozenset({DeviceType.SCALE}),
    AssignmentRole.SCANNER: frozenset({DeviceType.BARCODE_SCANNER, DeviceType.QR_SCANNER}),
    AssignmentRole.CASH_DRAWER: frozenset({DeviceType.CASH_DRAWER}),
    AssignmentRole.PAYMENT_TERMINAL: frozenset({DeviceType.PAYMENT_TERMINAL}),
    AssignmentRole.CUSTOMER_DISPLAY: frozenset({DeviceType.CUSTOMER_DISPLAY}),
}


class DeviceCapabilityCode(str, Enum):
    """What a device profile can do. The first eight are §23's printer
    capabilities (cut/drawer_pulse/qr/barcode/image/unicode/color/duplex);
    the rest extend the same idea to the other device types §18 lists."""

    CUT = "CUT"
    DRAWER_PULSE = "DRAWER_PULSE"
    QR = "QR"
    BARCODE = "BARCODE"
    IMAGE = "IMAGE"
    UNICODE = "UNICODE"
    COLOR = "COLOR"
    DUPLEX = "DUPLEX"
    WEIGH = "WEIGH"
    TARE = "TARE"
    SCAN_1D = "SCAN_1D"
    SCAN_2D = "SCAN_2D"
    DISPENSE_CASH = "DISPENSE_CASH"
    ACCEPT_CASH = "ACCEPT_CASH"
    CARD_SWIPE = "CARD_SWIPE"
    CARD_CHIP = "CARD_CHIP"
    CARD_CONTACTLESS = "CARD_CONTACTLESS"
    DISPLAY_TEXT = "DISPLAY_TEXT"
    DISPLAY_IMAGE = "DISPLAY_IMAGE"
    TEMPERATURE_READ = "TEMPERATURE_READ"


class PaperProfileType(str, Enum):
    """Named paper/output profiles a printer `DeviceProfile` declares.
    See §23."""

    PAPER_58MM = "PAPER_58MM"
    PAPER_80MM = "PAPER_80MM"
    A4 = "A4"
    LETTER = "LETTER"
    LABEL = "LABEL"
    CARD = "CARD"
    PDF = "PDF"
    VIRTUAL = "VIRTUAL"


class PrinterProtocol(str, Enum):
    """§23: "No asumir que toda impresora es ESC/POS." — a printer
    profile's `protocol`, when set, must be one of these, not an
    unvalidated free string."""

    ESC_POS = "ESC_POS"
    ZPL = "ZPL"
    PDF = "PDF"
    HTML = "HTML"
    RAW = "RAW"
    VIRTUAL = "VIRTUAL"


# Device types that are printers — the only ones a PrintRoute/printer
# profile validation may target. See §18/§23.
PRINTER_DEVICE_TYPES = frozenset({
    DeviceType.THERMAL_PRINTER, DeviceType.LABEL_PRINTER,
    DeviceType.DOCUMENT_PRINTER, DeviceType.CARD_PRINTER,
})

# §22: device types this SET's scale-specific validation applies to.
SCALE_DEVICE_TYPES = frozenset({DeviceType.SCALE})

# §18/§22: barcode/QR readers, grouped with scales in "Básculas y lectores".
READER_DEVICE_TYPES = frozenset({DeviceType.BARCODE_SCANNER, DeviceType.QR_SCANNER})

# §18/§20: device types this SET-10 (Cajones y terminales) validation applies to.
CASH_DRAWER_DEVICE_TYPES = frozenset({DeviceType.CASH_DRAWER})
PAYMENT_TERMINAL_DEVICE_TYPES = frozenset({DeviceType.PAYMENT_TERMINAL})

# A payment terminal profile must declare at least one of these — a
# terminal that can neither read a card nor accept/dispense cash isn't a
# payment terminal.
PAYMENT_TERMINAL_CAPABILITIES = frozenset({
    DeviceCapabilityCode.CARD_SWIPE, DeviceCapabilityCode.CARD_CHIP,
    DeviceCapabilityCode.CARD_CONTACTLESS, DeviceCapabilityCode.ACCEPT_CASH,
    DeviceCapabilityCode.DISPENSE_CASH,
})


class WeightUnit(str, Enum):
    """§22's "unidad" — the unit a `WeightReading` is expressed in."""

    KG = "KG"
    G = "G"
    LB = "LB"
    OZ = "OZ"


class ScaleProtocol(str, Enum):
    """§22's "protocolo" — how a scale reports weight over the wire.
    Mirrors `PrinterProtocol`'s "don't assume one protocol" stance for
    printers (§23) applied to scales."""

    TOLEDO_STANDARD = "TOLEDO_STANDARD"
    SICS = "SICS"
    NCI = "NCI"
    CONTINUOUS = "CONTINUOUS"
    ON_DEMAND = "ON_DEMAND"
    VIRTUAL = "VIRTUAL"
