"""Born-clean Cash Register schema: UUIDv7, Decimal TEXT, no legacy backfill."""
from __future__ import annotations

UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"
U = UUID_CHECK.format

DDL = (
    f"""CREATE TABLE IF NOT EXISTS cash_registers (
        id TEXT PRIMARY KEY CHECK({U('id')}), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        name TEXT NOT NULL CHECK(trim(name)<>''), status TEXT NOT NULL CHECK(status IN ('ACTIVE','INACTIVE','BLOCKED')),
        blocked_reason TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        UNIQUE(branch_id,name))""",
    f"""CREATE TABLE IF NOT EXISTS cash_drawers (
        id TEXT PRIMARY KEY CHECK({U('id')}), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        register_id TEXT NOT NULL REFERENCES cash_registers(id), name TEXT NOT NULL CHECK(trim(name)<>''),
        status TEXT NOT NULL CHECK(status IN ('ACTIVE','INACTIVE','BLOCKED')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(register_id,name))""",
    f"""CREATE TABLE IF NOT EXISTS pos_terminals (
        id TEXT PRIMARY KEY CHECK({U('id')}), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        register_id TEXT NOT NULL REFERENCES cash_registers(id), name TEXT NOT NULL CHECK(trim(name)<>''),
        status TEXT NOT NULL CHECK(status IN ('ACTIVE','INACTIVE','BLOCKED')),
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(register_id,name))""",
    f"""CREATE TABLE IF NOT EXISTS cash_shifts (
        id TEXT PRIMARY KEY CHECK({U('id')}), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        register_id TEXT NOT NULL REFERENCES cash_registers(id), drawer_id TEXT NOT NULL REFERENCES cash_drawers(id),
        terminal_id TEXT NOT NULL REFERENCES pos_terminals(id), cashier_user_id TEXT NOT NULL CHECK({U('cashier_user_id')}),
        opening_amount TEXT NOT NULL CHECK(trim(opening_amount)<>'' AND CAST(opening_amount AS NUMERIC)>=0),
        opening_operation_id TEXT NOT NULL UNIQUE CHECK({U('opening_operation_id')} AND opening_operation_id<>id),
        status TEXT NOT NULL CHECK(status IN ('OPEN','SUSPENDED','CLOSING','CLOSED')),
        opened_at TEXT NOT NULL, suspended_reason TEXT,
        z_cut_id TEXT REFERENCES cash_cuts(id) DEFERRABLE INITIALLY DEFERRED, closed_at TEXT,
        CHECK((status='CLOSED' AND z_cut_id IS NOT NULL AND closed_at IS NOT NULL) OR status<>'CLOSED'))""",
    f"""CREATE TABLE IF NOT EXISTS cash_ledger_entries (
        id TEXT PRIMARY KEY CHECK({U('id')}), shift_id TEXT NOT NULL REFERENCES cash_shifts(id),
        branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        movement_type TEXT NOT NULL CHECK(movement_type IN ('OPENING_FLOAT','CASH_SALE','CASH_REFUND','MANUAL_INCOME','MANUAL_WITHDRAWAL','SAFE_DROP','HANDOVER','REVERSAL','ADJUSTMENT')),
        direction TEXT NOT NULL CHECK(direction IN ('INFLOW','OUTFLOW')),
        amount TEXT NOT NULL CHECK(trim(amount)<>'' AND CAST(amount AS NUMERIC)>0),
        operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')} AND operation_id<>id),
        recorded_by TEXT NOT NULL CHECK({U('recorded_by')}),
        concept TEXT NOT NULL DEFAULT '', reference_id TEXT,
        reversal_of_id TEXT REFERENCES cash_ledger_entries(id), related_sale_id TEXT,
        recorded_at TEXT NOT NULL,
        CHECK(reversal_of_id IS NULL OR movement_type='REVERSAL'),
        CHECK(movement_type NOT IN ('MANUAL_INCOME','MANUAL_WITHDRAWAL','SAFE_DROP') OR trim(concept)<>''))""",
    f"""CREATE TABLE IF NOT EXISTS cash_counts (
        id TEXT PRIMARY KEY CHECK({U('id')}), shift_id TEXT NOT NULL REFERENCES cash_shifts(id),
        branch_id TEXT NOT NULL CHECK({U('branch_id')}), counter_user_id TEXT NOT NULL CHECK({U('counter_user_id')}),
        operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')} AND operation_id<>id),
        denominations_json TEXT NOT NULL DEFAULT '{{}}', total_counted TEXT NOT NULL CHECK(CAST(total_counted AS NUMERIC)>=0),
        status TEXT NOT NULL CHECK(status IN ('OPEN','CONFIRMED','CANCELLED')), confirmed_at TEXT,
        CHECK((status='CONFIRMED' AND confirmed_at IS NOT NULL) OR status<>'CONFIRMED'))""",
    f"""CREATE TABLE IF NOT EXISTS cash_count_denominations (
        id TEXT PRIMARY KEY CHECK({U('id')}), count_id TEXT NOT NULL REFERENCES cash_counts(id) ON DELETE CASCADE,
        denomination_id TEXT NOT NULL REFERENCES cash_denominations(id),
        denomination TEXT NOT NULL CHECK(CAST(denomination AS NUMERIC)>0),
        quantity INTEGER NOT NULL CHECK(quantity>=0), subtotal TEXT NOT NULL CHECK(CAST(subtotal AS NUMERIC)>=0),
        UNIQUE(count_id,denomination_id), UNIQUE(count_id,denomination))""",
    f"""CREATE TABLE IF NOT EXISTS cash_cuts (
        id TEXT PRIMARY KEY CHECK({U('id')}), shift_id TEXT NOT NULL REFERENCES cash_shifts(id),
        branch_id TEXT NOT NULL CHECK({U('branch_id')}), cut_type TEXT NOT NULL CHECK(cut_type IN ('X','Z')),
        document_number TEXT NOT NULL UNIQUE CHECK(trim(document_number)<>''), snapshot_json TEXT NOT NULL DEFAULT '{{}}',
        generated_by TEXT NOT NULL CHECK({U('generated_by')}), expected_cash TEXT NOT NULL CHECK(CAST(expected_cash AS NUMERIC)>=0),
        counted_cash TEXT CHECK(counted_cash IS NULL OR CAST(counted_cash AS NUMERIC)>=0), difference TEXT,
        blind_count_id TEXT REFERENCES cash_counts(id), operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')} AND operation_id<>id),
        is_final INTEGER NOT NULL CHECK(is_final IN (0,1)), generated_at TEXT NOT NULL,
        CHECK((cut_type='X' AND is_final=0 AND counted_cash IS NULL AND blind_count_id IS NULL) OR
              (cut_type='Z' AND is_final=1 AND counted_cash IS NOT NULL AND difference IS NOT NULL AND blind_count_id IS NOT NULL)))""",
    f"""CREATE TABLE IF NOT EXISTS cash_differences (
        id TEXT PRIMARY KEY CHECK({U('id')}), shift_id TEXT NOT NULL REFERENCES cash_shifts(id),
        z_cut_id TEXT NOT NULL UNIQUE REFERENCES cash_cuts(id), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        expected_amount TEXT NOT NULL CHECK(CAST(expected_amount AS NUMERIC)>=0),
        counted_amount TEXT NOT NULL CHECK(CAST(counted_amount AS NUMERIC)>=0), amount TEXT NOT NULL,
        detected_by TEXT NOT NULL CHECK({U('detected_by')}), operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')} AND operation_id<>id),
        responsible_user_id TEXT NOT NULL CHECK({U('responsible_user_id')}),
        classification TEXT NOT NULL CHECK(classification IN ('SHORTAGE','OVERAGE')),
        severity TEXT NOT NULL CHECK(severity IN ('WITHIN_TOLERANCE','REVIEW','CRITICAL')),
        tolerance_amount TEXT NOT NULL CHECK(CAST(tolerance_amount AS NUMERIC)>=0),
        recurrence_count INTEGER NOT NULL CHECK(recurrence_count>0),
        status TEXT NOT NULL CHECK(status IN ('DETECTED','EXPLAINED','UNDER_REVIEW','RESOLVED')),
        explanation TEXT, explained_by TEXT, reviewed_by TEXT, resolution TEXT, resolved_by TEXT,
        CHECK(reviewed_by IS NULL OR (reviewed_by<>detected_by AND reviewed_by<>explained_by)),
        CHECK(resolved_by IS NULL OR (resolved_by<>detected_by AND resolved_by<>explained_by AND resolved_by<>reviewed_by)))""",
    f"""CREATE TABLE IF NOT EXISTS cash_handovers (
        id TEXT PRIMARY KEY CHECK({U('id')}), shift_id TEXT NOT NULL REFERENCES cash_shifts(id),
        branch_id TEXT NOT NULL CHECK({U('branch_id')}), amount TEXT NOT NULL CHECK(CAST(amount AS NUMERIC)>0),
        prepared_by TEXT NOT NULL CHECK({U('prepared_by')}), delivered_by TEXT, received_by TEXT,
        operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')} AND operation_id<>id),
        source_entry_id TEXT NOT NULL UNIQUE REFERENCES cash_ledger_entries(id),
        status TEXT NOT NULL CHECK(status IN ('PREPARED','DELIVERED','RECEIVED','DISPUTED')),
        prepared_at TEXT NOT NULL, delivered_at TEXT, received_at TEXT,
        disputed_by TEXT, disputed_at TEXT, dispute_reason TEXT,
        CHECK(received_by IS NULL OR received_by<>delivered_by))""",
    f"""CREATE TABLE IF NOT EXISTS cash_handover_denominations (
        id TEXT PRIMARY KEY CHECK({U('id')}), handover_id TEXT NOT NULL REFERENCES cash_handovers(id) ON DELETE CASCADE,
        denomination_id TEXT NOT NULL REFERENCES cash_denominations(id),
        denomination TEXT NOT NULL CHECK(CAST(denomination AS NUMERIC)>0),
        quantity INTEGER NOT NULL CHECK(quantity>=0), subtotal TEXT NOT NULL CHECK(CAST(subtotal AS NUMERIC)>=0),
        UNIQUE(handover_id,denomination_id))""",
    f"""CREATE TABLE IF NOT EXISTS cash_handover_confirmations (
        id TEXT PRIMARY KEY CHECK({U('id')}), handover_id TEXT NOT NULL REFERENCES cash_handovers(id),
        confirmation_type TEXT NOT NULL CHECK(confirmation_type IN ('DELIVERY','RECEPTION','DISPUTE')),
        confirmed_by TEXT NOT NULL CHECK({U('confirmed_by')}), operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')}),
        denominations_json TEXT NOT NULL, total_amount TEXT NOT NULL CHECK(CAST(total_amount AS NUMERIC)>=0),
        notes TEXT NOT NULL DEFAULT '', confirmed_at TEXT NOT NULL, UNIQUE(handover_id,confirmation_type))""",
    f"""CREATE TABLE IF NOT EXISTS cash_authorization_grants (
        id TEXT PRIMARY KEY CHECK({U('id')}), requested_by TEXT NOT NULL CHECK({U('requested_by')}),
        authorized_by TEXT NOT NULL CHECK({U('authorized_by')}), permission_code TEXT NOT NULL CHECK(trim(permission_code)<>''),
        reason TEXT NOT NULL CHECK(trim(reason)<>''), operation_id TEXT NOT NULL CHECK({U('operation_id')}),
        entity_id TEXT NOT NULL CHECK({U('entity_id')}), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        amount TEXT CHECK(amount IS NULL OR CAST(amount AS NUMERIC)>=0), device_id TEXT, authorized_at TEXT NOT NULL,
        CHECK(requested_by<>authorized_by), UNIQUE(operation_id,permission_code))""",
    f"""CREATE TABLE IF NOT EXISTS cash_audit_log (
        id TEXT PRIMARY KEY CHECK({U('id')}), action TEXT NOT NULL CHECK(trim(action)<>''),
        actor_user_id TEXT NOT NULL CHECK({U('actor_user_id')}), entity_id TEXT NOT NULL CHECK({U('entity_id')}),
        branch_id TEXT NOT NULL CHECK({U('branch_id')}), operation_id TEXT NOT NULL CHECK({U('operation_id')}),
        reason TEXT NOT NULL, authorization_id TEXT REFERENCES cash_authorization_grants(id),
        amount TEXT, device_id TEXT, before_json TEXT, after_json TEXT, occurred_at TEXT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS cash_domain_events (
        id TEXT PRIMARY KEY CHECK({U('id')}), event_name TEXT NOT NULL CHECK(event_name LIKE 'CASH_%'),
        operation_id TEXT NOT NULL CHECK({U('operation_id')}), entity_id TEXT NOT NULL CHECK({U('entity_id')}),
        branch_id TEXT NOT NULL CHECK({U('branch_id')}), user_id TEXT NOT NULL CHECK({U('user_id')}),
        occurred_at TEXT NOT NULL, payload_json TEXT NOT NULL CHECK(trim(payload_json)<>''),
        CHECK(id<>operation_id AND id<>entity_id AND operation_id<>entity_id),
        UNIQUE(event_name,operation_id,entity_id))""",
    f"""CREATE TABLE IF NOT EXISTS cash_outbox (
        id TEXT PRIMARY KEY CHECK({U('id')}), event_id TEXT NOT NULL UNIQUE REFERENCES cash_domain_events(id),
        event_name TEXT NOT NULL CHECK(event_name LIKE 'CASH_%'), operation_id TEXT NOT NULL UNIQUE CHECK({U('operation_id')}),
        entity_id TEXT NOT NULL CHECK({U('entity_id')}), payload_json TEXT NOT NULL CHECK(trim(payload_json)<>''),
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PROCESSING','DISPATCHED','FAILED','DEAD_LETTER')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0), created_at TEXT NOT NULL,
        next_attempt_at TEXT, dispatched_at TEXT, last_error TEXT,
        CHECK(id<>event_id AND id<>operation_id AND event_id<>operation_id AND event_id<>entity_id))""",
    f"""CREATE TABLE IF NOT EXISTS cash_processed_operations (
        operation_id TEXT PRIMARY KEY CHECK({U('operation_id')}), operation_type TEXT NOT NULL CHECK(trim(operation_type)<>''),
        result_entity_id TEXT NOT NULL CHECK({U('result_entity_id')}), result_json TEXT NOT NULL,
        processed_at TEXT NOT NULL, CHECK(operation_id<>result_entity_id))""",
    f"""CREATE TABLE IF NOT EXISTS cash_sync_devices (
        id TEXT PRIMARY KEY CHECK({U('id')}), branch_id TEXT NOT NULL CHECK({U('branch_id')}),
        local_sequence INTEGER NOT NULL DEFAULT 0 CHECK(local_sequence>=0),
        last_synced_sequence INTEGER NOT NULL DEFAULT 0 CHECK(last_synced_sequence>=0 AND last_synced_sequence<=local_sequence),
        connectivity TEXT NOT NULL CHECK(connectivity IN ('ONLINE','OFFLINE')),
        sync_status TEXT NOT NULL CHECK(sync_status IN ('IDLE','SYNCING','RETRYING','CONFLICT','ERROR')),
        last_error TEXT, last_sync_at TEXT, updated_at TEXT NOT NULL)""",
    f"""CREATE TABLE IF NOT EXISTS cash_sync_envelopes (
        id TEXT PRIMARY KEY CHECK({U('id')}), outbox_id TEXT NOT NULL UNIQUE REFERENCES cash_outbox(id),
        device_id TEXT NOT NULL REFERENCES cash_sync_devices(id),
        sequence_no INTEGER NOT NULL CHECK(sequence_no>0), aggregate_version INTEGER NOT NULL CHECK(aggregate_version>0),
        state TEXT NOT NULL CHECK(state IN ('PENDING','IN_FLIGHT','RETRY','SYNCED','CONFLICT')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0), next_attempt_at TEXT,
        remote_revision TEXT, conflict_json TEXT, created_at TEXT NOT NULL, synced_at TEXT,
        UNIQUE(device_id,sequence_no))""",
)

INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_shift_active_register ON cash_shifts(register_id) WHERE status IN ('OPEN','SUSPENDED','CLOSING')",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_shift_active_drawer ON cash_shifts(drawer_id) WHERE status IN ('OPEN','SUSPENDED','CLOSING')",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_shift_active_terminal ON cash_shifts(terminal_id) WHERE status IN ('OPEN','SUSPENDED','CLOSING')",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_shift_active_cashier ON cash_shifts(cashier_user_id) WHERE status IN ('OPEN','SUSPENDED','CLOSING')",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_final_z_cut ON cash_cuts(shift_id) WHERE cut_type='Z' AND is_final=1",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_count_open_shift ON cash_counts(shift_id) WHERE status='OPEN'",
    "CREATE INDEX IF NOT EXISTS idx_cash_ledger_shift_time ON cash_ledger_entries(shift_id,recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_cash_ledger_reference ON cash_ledger_entries(reference_id,movement_type)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_ledger_single_reversal ON cash_ledger_entries(reversal_of_id) WHERE reversal_of_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_ledger_sale_reference ON cash_ledger_entries(reference_id) WHERE movement_type='CASH_SALE'",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_cash_ledger_refund_reference ON cash_ledger_entries(reference_id) WHERE movement_type='CASH_REFUND'",
    "CREATE INDEX IF NOT EXISTS idx_cash_ledger_refund_sale ON cash_ledger_entries(related_sale_id,movement_type)",
    "CREATE INDEX IF NOT EXISTS idx_cash_counts_shift_status ON cash_counts(shift_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_cash_differences_scope_status ON cash_differences(branch_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_cash_handovers_scope_status ON cash_handovers(branch_id,status)",
    "CREATE INDEX IF NOT EXISTS idx_cash_handover_confirmation ON cash_handover_confirmations(handover_id,confirmation_type)",
    "CREATE INDEX IF NOT EXISTS idx_cash_audit_operation ON cash_audit_log(operation_id,occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_cash_events_operation ON cash_domain_events(operation_id,occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_cash_outbox_dispatch ON cash_outbox(status,next_attempt_at,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_cash_sync_ready ON cash_sync_envelopes(device_id,state,next_attempt_at,sequence_no)",
    "CREATE INDEX IF NOT EXISTS idx_cash_sync_conflicts ON cash_sync_envelopes(device_id,state,sequence_no)",
)


def run(connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        for statement in DDL:
            connection.execute(statement)
        for statement in INDEXES:
            connection.execute(statement)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"CASH-3 foreign-key violations: {violations}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


up = run
