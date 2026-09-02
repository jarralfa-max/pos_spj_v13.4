"""TemplateActivationPolicy — SET-11 (§26): only one ACTIVE version per
template at a time. `DocumentTemplateVersion.activate()` only knows about
its own state; this policy is the one place that supersedes whatever
version was previously ACTIVE for the same template — the same
orchestration split `policies/configuration_rollback_policy.py` uses in
Settings (the entity offers valid single-object transitions, a policy
coordinates across two objects).
"""

from __future__ import annotations

from backend.domain.document_output.entities.document_template_version import DocumentTemplateVersion
from backend.domain.document_output.exceptions import DocumentInvalidValueError


def activate_version(
    new_version: DocumentTemplateVersion, *, activated_by_user_id: str,
    currently_active_version: DocumentTemplateVersion | None = None,
) -> None:
    if currently_active_version is not None and currently_active_version.template_id != new_version.template_id:
        raise DocumentInvalidValueError(
            "currently_active_version pertenece a otra plantilla — no puede supersederse aquí"
        )
    if currently_active_version is not None and currently_active_version.id == new_version.id:
        raise DocumentInvalidValueError("new_version ya es la versión activa")

    new_version.activate(activated_by_user_id)
    if currently_active_version is not None:
        currently_active_version.expire()
