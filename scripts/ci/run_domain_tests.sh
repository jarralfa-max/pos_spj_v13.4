#!/usr/bin/env bash
set -euo pipefail

DOMAIN="${1:-ventas}"

case "$DOMAIN" in
  ventas)
    python -m pytest pos_spj_v13.4/tests/test_payment_method_normalization.py \
      pos_spj_v13.4/tests/test_loyalty_single_accrual.py \
      pos_spj_v13.4/tests/test_loyalty_redemption_transactional.py \
      pos_spj_v13.4/tests/test_procesar_venta_uc_no_duplicate_side_effects.py \
      pos_spj_v13.4/tests/test_sales_service_single_event_flow.py \
      pos_spj_v13.4/tests/test_sales_no_duplication_real.py \
      pos_spj_v13.4/tests/test_legacy_venta_repository_guardrail.py \
      pos_spj_v13.4/tests/test_mercado_pago_pending_flow.py \
      pos_spj_v13.4/tests/test_mercado_pago_webhook_confirmation.py -q
    ;;
  ui)
    python -m pytest \
      pos_spj_v13.4/tests/test_ui_does_not_publish_inventory_business_events.py \
      pos_spj_v13.4/tests/test_mercado_pago_pending_flow.py -q
    ;;
  api)
    python -m pytest pos_spj_v13.4/tests -q \
      --ignore=pos_spj_v13.4/tests/test_delivery_action_policy.py
    ;;
  *)
    echo "Unknown domain: $DOMAIN" >&2
    exit 2
    ;;
esac
