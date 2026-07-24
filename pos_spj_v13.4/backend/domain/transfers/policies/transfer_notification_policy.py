"""Configuration-driven notification decisions for canonical transfer facts."""
from dataclasses import dataclass
from enum import Enum


class TransferAlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    DANGER = "DANGER"
    CRITICAL = "CRITICAL"


class TransferNotificationChannel(str, Enum):
    IN_APP = "IN_APP"
    WHATSAPP = "WHATSAPP"


@dataclass(frozen=True, slots=True)
class TransferNotificationRule:
    event_name: str
    severity: TransferAlertSeverity
    recipient_roles: tuple[str, ...]
    whatsapp_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.event_name or not self.recipient_roles:
            raise ValueError("Notification rules require an event and recipient roles")


class TransferNotificationPolicy:
    def __init__(self, rules: tuple[TransferNotificationRule, ...]) -> None:
        if len({rule.event_name for rule in rules}) != len(rules):
            raise ValueError("Only one notification rule is allowed per event")
        self._rules = {rule.event_name: rule for rule in rules}

    def rule_for(self, event_name: str) -> TransferNotificationRule | None:
        return self._rules.get(event_name)

    def channels_for(self, rule: TransferNotificationRule) -> tuple[TransferNotificationChannel, ...]:
        channels = [TransferNotificationChannel.IN_APP]
        if rule.whatsapp_enabled and rule.severity in {
                TransferAlertSeverity.DANGER, TransferAlertSeverity.CRITICAL}:
            channels.append(TransferNotificationChannel.WHATSAPP)
        return tuple(channels)
