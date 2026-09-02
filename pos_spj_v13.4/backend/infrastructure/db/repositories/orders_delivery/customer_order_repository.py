"""CustomerOrderRepository — persists/reconstructs the `CustomerOrder`
aggregate (with its `CustomerOrderLine`s) against the `customer_orders`/
`customer_order_lines` tables from
backend/infrastructure/db/schema/orders_delivery_schema.py (ORD-3).

Concrete class, no `Protocol` port — mirrors `SaleRepository`'s convention.
`save()` replaces all of an order's lines wholesale on every call (same
delete-then-reinsert shape as `SaleRepository.save()`). `get()` does two
separate queries (header, then lines ordered by creation) — no JOIN.

Never commits — OrdersDeliveryUnitOfWork owns the transaction boundary.
"""

from __future__ import annotations

import json

from backend.domain.orders_delivery.entities import CustomerOrder, CustomerOrderLine
from backend.domain.orders_delivery.enums import (
    CustomerApprovalStatus,
    FulfillmentStatus,
    FulfillmentType,
    OrderChannel,
    OrderLineStatus,
    OrderStatus,
    OrderType,
    PaymentStatus,
    PreparationStatus,
    ScheduleStatus,
    SubstitutionType,
)
from backend.domain.orders_delivery.value_objects.order_quantity import OrderQuantity
from backend.domain.orders_delivery.value_objects.order_totals import OrderTotals
from backend.infrastructure.db.repositories.orders_delivery.base import (
    OrdersDeliveryRepositoryBase,
    dec_str,
    enum_value,
    opt_dec_str,
    to_decimal,
)


def _snapshot_to_json(snapshot) -> str:
    return json.dumps(dict(snapshot or {}), ensure_ascii=False, sort_keys=True,
                       separators=(",", ":"))


def _snapshot_from_json(raw: str | None) -> dict:
    if not raw:
        return {}
    return json.loads(raw)


def _opt_quantity(value: str | None, unit: str | None) -> OrderQuantity | None:
    if value is None:
        return None
    return OrderQuantity(to_decimal(value), unit=unit or "PZA")


class CustomerOrderRepository(OrdersDeliveryRepositoryBase):
    def save(self, order: CustomerOrder) -> None:
        self._execute(
            """
            INSERT INTO customer_orders (
                id, order_number, branch_id, channel, order_type, fulfillment_type,
                customer_id, contact_name, contact_phone, delivery_address_id,
                requested_delivery_window, scheduled_for,
                delivery_window_start, delivery_window_end, activation_at, schedule_status,
                preparation_status, assigned_to_user_id, station_id,
                preparation_started_at, preparation_completed_at,
                pickup_verification_code,
                priority,
                status, payment_status, fulfillment_status, customer_approval_status,
                customer_approval_expires_at,
                currency_code, subtotal, discount_total, delivery_fee, tax_total,
                rounding_adjustment, grand_total,
                external_order_reference, sale_id, quote_id, whatsapp_order_id,
                operation_id, created_by_user_id, confirmed_by_user_id,
                cancelled_by_user_id, created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                order_number=excluded.order_number,
                contact_name=excluded.contact_name,
                contact_phone=excluded.contact_phone,
                delivery_address_id=excluded.delivery_address_id,
                requested_delivery_window=excluded.requested_delivery_window,
                scheduled_for=excluded.scheduled_for,
                delivery_window_start=excluded.delivery_window_start,
                delivery_window_end=excluded.delivery_window_end,
                activation_at=excluded.activation_at,
                schedule_status=excluded.schedule_status,
                preparation_status=excluded.preparation_status,
                assigned_to_user_id=excluded.assigned_to_user_id,
                station_id=excluded.station_id,
                preparation_started_at=excluded.preparation_started_at,
                preparation_completed_at=excluded.preparation_completed_at,
                pickup_verification_code=excluded.pickup_verification_code,
                priority=excluded.priority,
                status=excluded.status,
                payment_status=excluded.payment_status,
                fulfillment_status=excluded.fulfillment_status,
                customer_approval_status=excluded.customer_approval_status,
                customer_approval_expires_at=excluded.customer_approval_expires_at,
                subtotal=excluded.subtotal,
                discount_total=excluded.discount_total,
                delivery_fee=excluded.delivery_fee,
                tax_total=excluded.tax_total,
                rounding_adjustment=excluded.rounding_adjustment,
                grand_total=excluded.grand_total,
                external_order_reference=excluded.external_order_reference,
                sale_id=excluded.sale_id,
                quote_id=excluded.quote_id,
                whatsapp_order_id=excluded.whatsapp_order_id,
                confirmed_by_user_id=excluded.confirmed_by_user_id,
                cancelled_by_user_id=excluded.cancelled_by_user_id,
                updated_at=excluded.updated_at
            """,
            (
                order.id, order.order_number, order.branch_id,
                enum_value(order.channel), enum_value(order.order_type),
                enum_value(order.fulfillment_type),
                order.customer_id, order.contact_name, order.contact_phone,
                order.delivery_address_id, order.requested_delivery_window,
                order.scheduled_for,
                order.delivery_window_start, order.delivery_window_end,
                order.activation_at, enum_value(order.schedule_status),
                enum_value(order.preparation_status), order.assigned_to_user_id,
                order.station_id, order.preparation_started_at, order.preparation_completed_at,
                order.pickup_verification_code,
                order.priority,
                enum_value(order.status), enum_value(order.payment_status),
                enum_value(order.fulfillment_status),
                enum_value(order.customer_approval_status),
                order.customer_approval_expires_at,
                order.currency_code,
                dec_str(order.totals.subtotal), dec_str(order.totals.discount_total),
                dec_str(order.totals.delivery_fee), dec_str(order.totals.tax_total),
                dec_str(order.totals.rounding_adjustment), dec_str(order.totals.grand_total),
                order.external_order_reference, order.sale_id, order.quote_id,
                order.whatsapp_order_id, order.operation_id,
                order.created_by_user_id, order.confirmed_by_user_id,
                order.cancelled_by_user_id, order.created_at, order.updated_at,
            ),
        )
        self._execute("DELETE FROM customer_order_lines WHERE order_id=?", (order.id,))
        for line in order.lines:
            self._execute(
                """
                INSERT INTO customer_order_lines (
                    id, order_id, product_id, variant_id,
                    requested_quantity, requested_quantity_unit,
                    requested_weight, requested_weight_unit,
                    prepared_quantity, prepared_quantity_unit,
                    prepared_weight, prepared_weight_unit,
                    final_quantity, final_quantity_unit,
                    final_weight, final_weight_unit,
                    unit_price_snapshot, discount_snapshot, tax_snapshot,
                    catch_weight_enabled, substitution_allowed,
                    substitution_type, substitute_product_id, substitution_reason,
                    pre_substitution_unit_price, proposed_substitution_unit_price,
                    customer_notes, preparation_notes, status, inventory_reservation_id,
                    package_id,
                    product_snapshot_json, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    line.id, line.order_id, line.product_id, line.variant_id,
                    opt_dec_str(line.requested_quantity.value if line.requested_quantity else None),
                    line.requested_quantity.unit if line.requested_quantity else None,
                    opt_dec_str(line.requested_weight.value if line.requested_weight else None),
                    line.requested_weight.unit if line.requested_weight else None,
                    opt_dec_str(line.prepared_quantity.value if line.prepared_quantity else None),
                    line.prepared_quantity.unit if line.prepared_quantity else None,
                    opt_dec_str(line.prepared_weight.value if line.prepared_weight else None),
                    line.prepared_weight.unit if line.prepared_weight else None,
                    opt_dec_str(line.final_quantity.value if line.final_quantity else None),
                    line.final_quantity.unit if line.final_quantity else None,
                    opt_dec_str(line.final_weight.value if line.final_weight else None),
                    line.final_weight.unit if line.final_weight else None,
                    dec_str(line.unit_price_snapshot), dec_str(line.discount_snapshot),
                    dec_str(line.tax_snapshot),
                    1 if line.catch_weight_enabled else 0,
                    1 if line.substitution_allowed else 0,
                    enum_value(line.substitution_type), line.substitute_product_id,
                    line.substitution_reason,
                    opt_dec_str(line.pre_substitution_unit_price),
                    opt_dec_str(line.proposed_substitution_unit_price),
                    line.customer_notes, line.preparation_notes,
                    enum_value(line.status), line.inventory_reservation_id,
                    line.package_id,
                    _snapshot_to_json(line.product_snapshot),
                    line.created_at, line.updated_at,
                ),
            )

    def get(self, order_id: str) -> CustomerOrder | None:
        header = self._query_one("SELECT * FROM customer_orders WHERE id=?", (order_id,))
        if header is None:
            return None
        return self._hydrate(header)

    def find_by_operation_id(self, operation_id: str) -> CustomerOrder | None:
        header = self._query_one(
            "SELECT * FROM customer_orders WHERE operation_id=?", (operation_id,))
        return self._hydrate(header) if header else None

    def find_by_channel_reference(
        self, *, channel: OrderChannel | str, external_order_reference: str,
    ) -> CustomerOrder | None:
        """§18 deduplication: the same channel + external reference (e.g. a
        WhatsApp message id, a webhook retry) must resolve to the SAME
        order, never create a second one."""
        header = self._query_one(
            "SELECT * FROM customer_orders WHERE channel=? AND external_order_reference=?",
            (enum_value(channel), external_order_reference))
        return self._hydrate(header) if header else None

    def _hydrate(self, header: dict) -> CustomerOrder:
        lines_rows = self._query(
            "SELECT * FROM customer_order_lines WHERE order_id=? ORDER BY created_at",
            (header["id"],))
        lines = [self._hydrate_line(row) for row in lines_rows]
        totals = OrderTotals(
            subtotal=to_decimal(header["subtotal"]),
            discount_total=to_decimal(header["discount_total"]),
            delivery_fee=to_decimal(header["delivery_fee"]),
            tax_total=to_decimal(header["tax_total"]),
            rounding_adjustment=to_decimal(header["rounding_adjustment"]),
            grand_total=to_decimal(header["grand_total"]),
        )
        return CustomerOrder(
            id=header["id"], order_number=header["order_number"],
            branch_id=header["branch_id"], channel=OrderChannel(header["channel"]),
            order_type=OrderType(header["order_type"]),
            fulfillment_type=FulfillmentType(header["fulfillment_type"]),
            customer_id=header["customer_id"], contact_name=header["contact_name"],
            contact_phone=header["contact_phone"],
            delivery_address_id=header["delivery_address_id"],
            requested_delivery_window=header["requested_delivery_window"],
            scheduled_for=header["scheduled_for"],
            delivery_window_start=header["delivery_window_start"],
            delivery_window_end=header["delivery_window_end"],
            activation_at=header["activation_at"],
            schedule_status=ScheduleStatus(header["schedule_status"]),
            preparation_status=PreparationStatus(header["preparation_status"]),
            assigned_to_user_id=header["assigned_to_user_id"],
            station_id=header["station_id"],
            preparation_started_at=header["preparation_started_at"],
            preparation_completed_at=header["preparation_completed_at"],
            pickup_verification_code=header["pickup_verification_code"],
            priority=header["priority"],
            status=OrderStatus(header["status"]),
            payment_status=PaymentStatus(header["payment_status"]),
            fulfillment_status=FulfillmentStatus(header["fulfillment_status"]),
            customer_approval_status=CustomerApprovalStatus(header["customer_approval_status"]),
            customer_approval_expires_at=header["customer_approval_expires_at"],
            currency_code=header["currency_code"], delivery_fee=to_decimal(header["delivery_fee"]),
            totals=totals,
            external_order_reference=header["external_order_reference"],
            sale_id=header["sale_id"], quote_id=header["quote_id"],
            whatsapp_order_id=header["whatsapp_order_id"], operation_id=header["operation_id"],
            created_by_user_id=header["created_by_user_id"],
            confirmed_by_user_id=header["confirmed_by_user_id"],
            cancelled_by_user_id=header["cancelled_by_user_id"],
            lines=lines, created_at=header["created_at"], updated_at=header["updated_at"],
        )

    @staticmethod
    def _hydrate_line(row: dict) -> CustomerOrderLine:
        return CustomerOrderLine(
            id=row["id"], order_id=row["order_id"], product_id=row["product_id"],
            variant_id=row["variant_id"],
            requested_quantity=_opt_quantity(row["requested_quantity"], row["requested_quantity_unit"]),
            requested_weight=_opt_quantity(row["requested_weight"], row["requested_weight_unit"]),
            prepared_quantity=_opt_quantity(row["prepared_quantity"], row["prepared_quantity_unit"]),
            prepared_weight=_opt_quantity(row["prepared_weight"], row["prepared_weight_unit"]),
            final_quantity=_opt_quantity(row["final_quantity"], row["final_quantity_unit"]),
            final_weight=_opt_quantity(row["final_weight"], row["final_weight_unit"]),
            unit_price_snapshot=to_decimal(row["unit_price_snapshot"]),
            discount_snapshot=to_decimal(row["discount_snapshot"]),
            tax_snapshot=to_decimal(row["tax_snapshot"]),
            catch_weight_enabled=bool(row["catch_weight_enabled"]),
            substitution_allowed=bool(row["substitution_allowed"]),
            substitution_type=(SubstitutionType(row["substitution_type"])
                                if row["substitution_type"] else None),
            substitute_product_id=row["substitute_product_id"],
            substitution_reason=row["substitution_reason"],
            pre_substitution_unit_price=(
                to_decimal(row["pre_substitution_unit_price"])
                if row["pre_substitution_unit_price"] is not None else None),
            proposed_substitution_unit_price=(
                to_decimal(row["proposed_substitution_unit_price"])
                if row["proposed_substitution_unit_price"] is not None else None),
            customer_notes=row["customer_notes"], preparation_notes=row["preparation_notes"],
            status=OrderLineStatus(row["status"]),
            inventory_reservation_id=row["inventory_reservation_id"],
            package_id=row["package_id"],
            product_snapshot=_snapshot_from_json(row["product_snapshot_json"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
