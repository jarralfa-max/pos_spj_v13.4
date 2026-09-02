"""PrinterProfilePolicy — is this `DeviceProfile` a legally-shaped
printer profile? (§23). `DeviceProfile` itself (SET-7) stays generic
across every device type — this policy adds the printer-specific rule
without forcing every non-printer profile through paper/protocol checks
that don't apply to it.
"""

from __future__ import annotations

from backend.domain.device_management.enums import PRINTER_DEVICE_TYPES, PaperProfileType, PrinterProtocol
from backend.domain.device_management.exceptions import InvalidPrinterProfileError


def assert_valid_printer_profile(profile) -> None:
    if profile.device_type not in PRINTER_DEVICE_TYPES:
        raise InvalidPrinterProfileError(
            f"{profile.device_type.value} no es un tipo de impresora "
            f"({sorted(t.value for t in PRINTER_DEVICE_TYPES)})"
        )
    if profile.paper_profile is not None:
        try:
            PaperProfileType(profile.paper_profile)
        except ValueError as exc:
            raise InvalidPrinterProfileError(
                f"paper_profile {profile.paper_profile!r} no es un perfil de papel canónico "
                f"({[p.value for p in PaperProfileType]})"
            ) from exc
    if profile.protocol:
        try:
            PrinterProtocol(profile.protocol)
        except ValueError as exc:
            raise InvalidPrinterProfileError(
                f"protocol {profile.protocol!r} no es un protocolo de impresora reconocido — "
                "no asumir que toda impresora es ESC/POS (§23)."
            ) from exc
