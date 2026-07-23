"""ExternalCatalogSource — a configured external catalog provider (§15).

Open Food Facts, a supplier catalog, a CSV feed: each is a source with a code,
provider type and endpoint/config. Records imported from it carry its id as their
provenance.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.domain.products.exceptions import InvalidExternalRecordError
from backend.domain.products.external_enums import ExternalProviderType
from backend.shared.ids import new_uuid


@dataclass
class ExternalCatalogSource:
    code: str
    name: str
    provider_type: ExternalProviderType
    id: str = field(default_factory=new_uuid)
    endpoint: str | None = None
    active: bool = True

    def __post_init__(self) -> None:
        code = (self.code or "").strip().upper()
        if not code:
            raise InvalidExternalRecordError("La fuente externa requiere un código")
        if not (self.name or "").strip():
            raise InvalidExternalRecordError("La fuente externa requiere un nombre")
        if not isinstance(self.provider_type, ExternalProviderType):
            try:
                self.provider_type = ExternalProviderType(str(self.provider_type))
            except ValueError as exc:
                raise InvalidExternalRecordError(
                    f"Proveedor externo inválido: {self.provider_type!r}") from exc
        object.__setattr__(self, "code", code)
