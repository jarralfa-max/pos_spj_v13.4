"""Segregación de funciones (§28).

- Quien crea un asiento manual no lo contabiliza cuando la revisión es obligatoria.
- Quien programa un pago no lo autoriza; quien lo autoriza no lo ejecuta cuando
  la configuración exige doble control; un pago sobre el umbral exige un segundo
  autorizador distinto del primero.
- Quien importa un estado bancario no aprueba ajustes de ese estado.

La política compara IDENTIDADES; los permisos (quién puede intentar cada paso)
los exige la capa de aplicación.
"""

from __future__ import annotations

from backend.domain.finance.entities.finance_settings import FinanceSettings
from backend.domain.finance.exceptions import SegregationOfDutiesError


def _same(a: str | None, b: str | None) -> bool:
    return bool(a) and bool(b) and str(a).strip() == str(b).strip()


class SegregationPolicy:
    def __init__(self, settings: FinanceSettings) -> None:
        self._settings = settings

    def enforce_journal_posting(self, *, created_by: str | None, posted_by: str | None) -> None:
        if self._settings.journal_review_required and _same(created_by, posted_by):
            raise SegregationOfDutiesError(
                "La revisión de asientos manuales es obligatoria: otra persona con permiso "
                "debe contabilizar el asiento que usted capturó")

    def enforce_payment_authorization(self, *, scheduled_by: str | None,
                                      authorizer: str | None,
                                      first_authorizer: str | None = None) -> None:
        if _same(scheduled_by, authorizer):
            raise SegregationOfDutiesError(
                "Quien programa un pago no puede autorizarlo")
        if _same(first_authorizer, authorizer):
            raise SegregationOfDutiesError(
                "La segunda autorización la da una persona distinta de la primera")

    def enforce_payment_execution(self, *, authorized_by: str | None,
                                  second_authorized_by: str | None,
                                  executor: str | None) -> None:
        if not self._settings.payment_dual_control:
            return
        if _same(authorized_by, executor) or _same(second_authorized_by, executor):
            raise SegregationOfDutiesError(
                "El doble control está activo: quien autoriza un pago no lo ejecuta")

    def enforce_statement_adjustment(self, *, imported_by: str | None,
                                     adjuster: str | None) -> None:
        if self._settings.statement_importer_cannot_adjust and _same(imported_by, adjuster):
            raise SegregationOfDutiesError(
                "Quien importó el estado de cuenta no aprueba ajustes de ese estado")

    def requires_second_authorization(self, amount) -> bool:
        threshold = self._settings.payment_second_authorization_threshold
        return threshold is not None and amount.amount >= threshold
