"""Root-cause methods and analysis invariants for LOSS-16."""

from dataclasses import dataclass
from enum import Enum

from backend.domain.losses.exceptions import LossInvariantError


class RootCauseMethod(str, Enum):
    FIVE_WHYS = "FIVE_WHYS"
    FISHBONE = "FISHBONE"
    PARETO = "PARETO"
    FAULT_TREE = "FAULT_TREE"
    DIRECT_OBSERVATION = "DIRECT_OBSERVATION"


@dataclass(frozen=True, slots=True)
class RootCauseSelection:
    catalog_entry_id: str
    rationale: str


@dataclass(frozen=True, slots=True)
class RootCauseAnalysis:
    method: RootCauseMethod
    summary: str
    primary_cause: RootCauseSelection
    contributing_causes: tuple[RootCauseSelection, ...]


class RootCausePolicy:
    @staticmethod
    def build(*, method, summary, primary_cause, contributing_causes):
        try: resolved_method = RootCauseMethod(method)
        except ValueError: raise LossInvariantError("Método de causa raíz no soportado") from None
        if not str(summary or "").strip(): raise LossInvariantError("El análisis requiere resumen")
        primary = RootCausePolicy._selection(primary_cause)
        contributors = tuple(RootCausePolicy._selection(item) for item in contributing_causes)
        identifiers = [primary.catalog_entry_id, *(item.catalog_entry_id for item in contributors)]
        if len(identifiers) != len(set(identifiers)):
            raise LossInvariantError("La causa primaria y las contribuyentes deben ser distintas")
        return RootCauseAnalysis(resolved_method,str(summary).strip(),primary,contributors)

    @staticmethod
    def _selection(item):
        if not str(item.catalog_entry_id or "").strip() or not str(item.rationale or "").strip():
            raise LossInvariantError("Cada causa requiere catálogo y justificación")
        return RootCauseSelection(item.catalog_entry_id,str(item.rationale).strip())
