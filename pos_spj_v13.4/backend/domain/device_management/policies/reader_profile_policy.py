"""ReaderProfilePolicy — is this `DeviceProfile` a legally-shaped
barcode/QR reader profile? (§18/§22 "lectores"). Simpler than printers/
scales — a reader has no paper profile, protocol taxonomy, or stability
concept, just "does it declare the scan capability its type implies".
"""

from __future__ import annotations

from backend.domain.device_management.enums import READER_DEVICE_TYPES, DeviceCapabilityCode, DeviceType
from backend.domain.device_management.exceptions import InvalidReaderProfileError

# Public (not module-private) — the registration use case reads this
# same mapping to auto-derive the required capability instead of making
# the caller guess it, so there's exactly one source of truth for
# "which capability does this reader type imply".
REQUIRED_CAPABILITY_BY_TYPE = {
    DeviceType.BARCODE_SCANNER: DeviceCapabilityCode.SCAN_1D,
    DeviceType.QR_SCANNER: DeviceCapabilityCode.SCAN_2D,
}


def assert_valid_reader_profile(profile) -> None:
    if profile.device_type not in READER_DEVICE_TYPES:
        raise InvalidReaderProfileError(
            f"{profile.device_type.value} no es un tipo de lector ({sorted(t.value for t in READER_DEVICE_TYPES)})"
        )
    required = REQUIRED_CAPABILITY_BY_TYPE[profile.device_type]
    if not profile.has_capability(required):
        raise InvalidReaderProfileError(
            f"{profile.name}: un perfil {profile.device_type.value} debe declarar la capacidad {required.value}"
        )
