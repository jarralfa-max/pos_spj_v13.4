"""LOSS-19 notification policies independent from delivery providers."""
from dataclasses import dataclass
from enum import Enum
class NotificationChannel(str,Enum):IN_APP="IN_APP";WHATSAPP="WHATSAPP"
@dataclass(frozen=True,slots=True)
class NotificationRule:roles:frozenset[str];channels:frozenset[NotificationChannel];severity:str
class LossNotificationPolicy:
    CRITICAL=frozenset({"LOSS_HIGH_VALUE_DETECTED","LOSS_QUALITY_CONDEMNED","LOSS_DISPOSITION_COMPLETED","YIELD_ALERT_RAISED","LOSS_FINANCE_RECOGNITION_REQUESTED"})
    OPERATIONAL=frozenset({"LOSS_CASE_SUBMITTED","LOSS_INVESTIGATION_OPENED","LOSS_CORRECTIVE_ACTION_CREATED","LOSS_CORRECTIVE_ACTION_SUBMITTED"})
    def rule_for(self,event_name):
        if event_name in self.CRITICAL:return NotificationRule(frozenset({"LOSSES_MANAGER","BRANCH_MANAGER"}),frozenset({NotificationChannel.IN_APP,NotificationChannel.WHATSAPP}),"CRITICAL")
        if event_name in self.OPERATIONAL:return NotificationRule(frozenset({"LOSSES_MANAGER"}),frozenset({NotificationChannel.IN_APP}),"ACTION_REQUIRED")
        return None
def valid_e164(value):
    phone=str(value or "")
    return phone.startswith("+") and phone[1:].isdigit() and 8<=len(phone[1:])<=15
