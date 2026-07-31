"""Canonical KPICard (FASE DS-3) — the single KPI implementation.

The component is presentation only: it never queries, sums, computes trends or
decides periods. It renders a ``KPIDTO`` produced by a QueryService/Presenter.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout

from frontend.desktop.components.tooltip import apply_tooltip
from frontend.desktop.themes.tokens import KpiMetrics, Spacing


class KPIState:
    LOADING = "LOADING"
    READY = "READY"
    EMPTY = "EMPTY"
    STALE = "STALE"
    ERROR = "ERROR"
    NO_PERMISSION = "NO_PERMISSION"
    OFFLINE = "OFFLINE"
    PARTIAL_DATA = "PARTIAL_DATA"


_STATE_PLACEHOLDER = {
    KPIState.LOADING: "…",
    KPIState.EMPTY: "—",
    KPIState.ERROR: "—",
    KPIState.NO_PERMISSION: "—",
    KPIState.OFFLINE: "—",
}


@dataclass(frozen=True)
class KPIDTO:
    key: str
    title: str
    value: str
    raw_value: Decimal | int | None = None
    icon: str | None = None
    variant: str = "neutral"
    trend_value: str | None = None
    trend_direction: str | None = None   # "up" | "down" | "flat"
    trend_label: str | None = None
    subtitle: str | None = None
    freshness: str | None = None
    state: str = KPIState.READY
    tooltip: str | None = None


_ARROW = {"up": "▲", "down": "▼", "flat": "→"}


def _value_text(dto: KPIDTO) -> str:
    if dto.state in (KPIState.READY, KPIState.STALE):
        return dto.value
    return _STATE_PLACEHOLDER.get(dto.state, dto.value)


def _subtitle_text(dto: KPIDTO) -> str:
    sub_bits = []
    if dto.trend_value and dto.trend_direction:
        sub_bits.append(f"{_ARROW.get(dto.trend_direction, '')} {dto.trend_value}"
                        + (f" {dto.trend_label}" if dto.trend_label else ""))
    if dto.subtitle:
        sub_bits.append(dto.subtitle)
    if dto.state == KPIState.STALE and dto.freshness:
        sub_bits.append(dto.freshness)
    return "  ·  ".join(sub_bits)


class KPICard(QFrame):
    def __init__(self, dto: KPIDTO, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setMinimumHeight(KpiMetrics.MIN_HEIGHT)
        self.setMaximumHeight(KpiMetrics.MAX_HEIGHT)
        self.setMinimumWidth(KpiMetrics.MIN_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.XXS)
        self._title = QLabel(self)
        self._title.setObjectName("kpiTitle")
        layout.addWidget(self._title)
        self._value = QLabel(self)
        self._value.setObjectName("kpiValue")
        layout.addWidget(self._value)
        self._subtitle = QLabel(self)
        self._subtitle.setObjectName("kpiSubtitle")
        self._subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self._subtitle)
        self.update(dto)

    @property
    def key(self) -> str:
        return self.dto.key

    def update(self, dto: KPIDTO) -> None:  # noqa: A003 — in-place refresh (§8.4)
        """Actualiza la tarjeta EN SITIO (sin recrear widgets) para el refresco por
        `key`; sólo reconstruye la fila si cambia el conjunto de KPIs."""
        self.dto = dto
        self.setProperty("variant", dto.variant)
        self._title.setText(dto.title)
        value_text = _value_text(dto)
        self._value.setText(value_text)
        sub = _subtitle_text(dto)
        self._subtitle.setText(sub)
        self._subtitle.setVisible(bool(sub))
        self.setAccessibleName(f"{dto.title}: {value_text}")
        if dto.tooltip:
            apply_tooltip(self, dto.tooltip, title=dto.title)
        # re-aplicar QSS al cambiar la variante
        self.style().unpolish(self)
        self.style().polish(self)
