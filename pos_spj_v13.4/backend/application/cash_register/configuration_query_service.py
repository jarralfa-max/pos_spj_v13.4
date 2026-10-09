"""Read models for the CASH-5 configuration page."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CashConfigurationRow:
    id: str
    name: str
    value: str
    scope: str
    effective_from: str
    effective_to: str
    status: str


class CashConfigurationReadRepository(Protocol):
    def list_configuration_rows(self, section: str) -> list[dict]: ...
    def alert_rule_options(self) -> list[dict]: ...
    def user_options(self) -> list[dict]: ...


@dataclass(frozen=True, slots=True)
class CashAlertRuleOption:
    id: str
    event_name: str
    channels: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CashUserOption:
    id: str
    name: str


class CashConfigurationQueryService:
    SECTIONS = frozenset({
        "hierarchy", "validity", "denominations", "payment_methods",
        "limits", "alerts", "whatsapp", "permissions", "reasons", "tolerances", "recipients",
    })

    def __init__(self, repository: CashConfigurationReadRepository) -> None:
        self._repository = repository

    def list_section(self, section: str) -> list[CashConfigurationRow]:
        if section not in self.SECTIONS:
            raise ValueError(f"Unknown Cash Register configuration section: {section}")
        return [CashConfigurationRow(
            id=str(row["id"]), name=str(row.get("name", "")),
            value=str(row.get("value", "")), scope=str(row.get("scope", "")),
            effective_from=str(row.get("effective_from", "")),
            effective_to=str(row.get("effective_to", "")),
            status=str(row.get("status", "")),
        ) for row in self._repository.list_configuration_rows(section)]


    def alert_rule_options(self) -> list[CashAlertRuleOption]:
        """Avisos vigentes, para elegir a cuál se agrega un destinatario."""
        return [CashAlertRuleOption(str(row["id"]), str(row["event_name"]),
                                    tuple(row["channels"]))
                for row in self._repository.alert_rule_options()]

    def user_options(self) -> list[CashUserOption]:
        return [CashUserOption(str(row["id"]), str(row["name"]))
                for row in self._repository.user_options()]
