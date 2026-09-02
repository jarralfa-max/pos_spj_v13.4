"""TemplateParameterPolicy — SET-20 "Templates": whether a supplied
params dict actually satisfies a `NotificationTemplate`'s declared
`parameter_names`. Generalizes the manual parameter-lookup loop
`whatsapp_service/messaging/templates.py::send_event_template` performs
(`for param_name in tmpl["params"]: ... params.get(param_name, "")` —
silently defaulting a missing parameter to an empty string) into an
explicit check that rejects the send instead of silently sending a
template with a blank slot.
"""

from __future__ import annotations

from backend.domain.notifications.entities.notification_template import NotificationTemplate
from backend.domain.notifications.exceptions import TemplateParameterMissingError


def assert_params_satisfied(template: NotificationTemplate, params: dict) -> None:
    missing = [name for name in template.parameter_names if not params.get(name)]
    if missing:
        raise TemplateParameterMissingError(
            f"La plantilla {template.code!r} requiere los parámetros {missing}, no fueron provistos"
        )
