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


class KPICard(QFrame):
    def __init__(self, dto: KPIDTO, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setProperty("variant", dto.variant)
        self.setMinimumHeight(KpiMetrics.MIN_HEIGHT)
        self.setMaximumHeight(KpiMetrics.MAX_HEIGHT)
        self.setMinimumWidth(KpiMetrics.MIN_WIDTH)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        layout.setSpacing(Spacing.XXS)

        title = QLabel(dto.title, self)
        title.setObjectName("kpiTitle")
        layout.addWidget(title)

        value_text = dto.value if dto.state == KPIState.READY or dto.state == KPIState.STALE \
            else _STATE_PLACEHOLDER.get(dto.state, dto.value)
        value = QLabel(value_text, self)
        value.setObjectName("kpiValue")
        layout.addWidget(value)

        sub_bits = []
        if dto.trend_value and dto.trend_direction:
            sub_bits.append(f"{_ARROW.get(dto.trend_direction, '')} {dto.trend_value}"
                            + (f" {dto.trend_label}" if dto.trend_label else ""))
        if dto.subtitle:
            sub_bits.append(dto.subtitle)
        if dto.state == KPIState.STALE and dto.freshness:
            sub_bits.append(dto.freshness)
        if sub_bits:
            subtitle = QLabel("  ·  ".join(sub_bits), self)
            subtitle.setObjectName("kpiSubtitle")
            subtitle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            layout.addWidget(subtitle)

        self.setAccessibleName(f"{dto.title}: {value_text}")
        if dto.tooltip:
            apply_tooltip(self, dto.tooltip, title=dto.title)
