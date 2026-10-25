"""Qué cupón o vale es lo que se escaneó o tecleó (auditoría de Fidelidad 968e0bc).

Un solo lugar decide, para el POS y para cualquier otro consumidor:

- **Código de pieza** (`VAL-…`/`CUP-…`): se busca por la HUELLA del código; la pieza
  debe estar activa, su lote vigente hoy y válido en esta sucursal.
- **Folio de una pieza** (`VAL7F3A-00001`): se rechaza. El folio es legible y está
  en reportes; no es prueba de que alguien tenga la pieza en la mano.
- **Código de un cupón o vale sin lote** (los emitidos uno por uno, los de
  devolución): se resuelve por su código, como siempre.

Sólo lee. Devuelve también el motivo de rechazo en lenguaje de cajero.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from backend.domain.commercial_instruments.entities.instrument_batch import InstrumentBatch
from backend.domain.commercial_instruments.value_objects.piece_code import (
    hash_piece_code,
    normalize_piece_code,
    piece_kind_prefix,
)

_PREFIX = {"COUPON": "CUP", "VOUCHER": "VAL"}
_LABEL = {"COUPON": "cupón", "VOUCHER": "vale"}


@dataclass(frozen=True)
class ResolvedInstrument:
    kind: str
    instance: object
    batch: InstrumentBatch | None = None
    item: dict | None = None

    @property
    def from_batch(self) -> bool:
        return self.batch is not None


def looks_like_piece(code: str) -> str | None:
    """`"COUPON"`/`"VOUCHER"` si el texto tiene forma de código de pieza."""
    canonico = normalize_piece_code(code)
    if canonico is None:
        return None
    return "COUPON" if piece_kind_prefix(canonico) == "CUP" else "VOUCHER"


def resolve_instrument(uow, code: str, *, kind: str, branch_id: str | None,
                       now: str | None = None) -> tuple[ResolvedInstrument | None, str]:
    etiqueta = _LABEL[kind]
    repo = uow.coupon_instances if kind == "COUPON" else uow.voucher_instances
    canonico = normalize_piece_code(code)
    if canonico is not None:
        if piece_kind_prefix(canonico) != _PREFIX[kind]:
            otro = "vale" if kind == "COUPON" else "cupón"
            return None, f"Ese código es de un {otro}, no de un {etiqueta}."
        item = uow.batch_items.get_by_token_hash(hash_piece_code(canonico))
        if item is None:
            return None, f"Código de {etiqueta} no reconocido o anulado."
        lote = uow.batches.get(item["batch_id"])
        if item["status"] == "REVOKED":
            return None, f"Ese {etiqueta} fue retirado ({item['folio']})."
        if item["status"] != "ACTIVE" or lote is None:
            return None, f"El lote de ese {etiqueta} todavía no está activo ({item['folio']})."
        instante = now or datetime.now(timezone.utc).isoformat(timespec="seconds")
        if not lote.valid_at(instante):
            return None, f"El {etiqueta} {item['folio']} está fuera de su vigencia."
        if branch_id and not lote.allows_branch(branch_id):
            return None, f"El {etiqueta} {item['folio']} no es válido en esta sucursal."
        instancia = repo.get(item["instance_id"])
        if instancia is None:
            return None, f"Código de {etiqueta} no reconocido o anulado."
        return ResolvedInstrument(kind=kind, instance=instancia, batch=lote, item=item), ""

    instancia = repo.get_by_code(str(code or "").strip())
    if instancia is None:
        return None, f"No existe un {etiqueta} con el código {str(code or '').strip()}"
    if uow.batch_items.get_for_instance(instancia.id) is not None:
        return None, (f"{str(code).strip()} es el folio de la pieza; escanea o teclea el "
                      f"código del {etiqueta}.")
    return ResolvedInstrument(kind=kind, instance=instancia), ""


__all__ = ["ResolvedInstrument", "looks_like_piece", "resolve_instrument"]
