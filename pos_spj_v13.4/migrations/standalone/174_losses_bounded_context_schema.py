"""Born-clean Losses bounded-context schema.

No legacy backfill, rescue tables, integer identities or dual writes. Decimal
values are stored as canonical TEXT and interpreted by the domain as Decimal.
"""

from __future__ import annotations

from backend.domain.losses.enums import LossClassificationCode, LossOrigin, LossStatus
from backend.shared.ids import new_uuid


def _values(enum_type) -> str:
    return ",".join(f"'{item.value}'" for item in enum_type)


CLASSIFICATIONS = _values(LossClassificationCode)
ORIGINS = _values(LossOrigin)
STATUSES = _values(LossStatus)
UUID_CHECK = "length({0})=36 AND lower({0})={0} AND substr({0},15,1)='7'"


DDL = (
    f"""CREATE TABLE IF NOT EXISTS loss_classifications (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        code TEXT NOT NULL UNIQUE CHECK(code IN ({CLASSIFICATIONS})),
        display_name TEXT NOT NULL CHECK(trim(display_name) <> ''),
        description TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_reasons (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        classification_id TEXT NOT NULL REFERENCES loss_classifications(id),
        code TEXT NOT NULL CHECK(trim(code) <> ''),
        display_name TEXT NOT NULL CHECK(trim(display_name) <> ''),
        description TEXT NOT NULL DEFAULT '',
        requires_evidence INTEGER NOT NULL DEFAULT 0 CHECK(requires_evidence IN (0,1)),
        requires_investigation INTEGER NOT NULL DEFAULT 0 CHECK(requires_investigation IN (0,1)),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        version INTEGER NOT NULL DEFAULT 1 CHECK(version > 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(classification_id, code),
        UNIQUE(id, classification_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_cases (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')} AND operation_id <> id),
        branch_id TEXT NOT NULL CHECK({UUID_CHECK.format('branch_id')}),
        warehouse_id TEXT NOT NULL CHECK({UUID_CHECK.format('warehouse_id')}),
        reported_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('reported_by_user_id')}),
        reviewed_by_user_id TEXT CHECK(reviewed_by_user_id IS NULL OR ({UUID_CHECK.format('reviewed_by_user_id')})),
        approved_by_user_id TEXT CHECK(approved_by_user_id IS NULL OR ({UUID_CHECK.format('approved_by_user_id')})),
        classification_id TEXT NOT NULL REFERENCES loss_classifications(id),
        reason_id TEXT NOT NULL,
        origin TEXT NOT NULL CHECK(origin IN ({ORIGINS})),
        status TEXT NOT NULL CHECK(status IN ({STATUSES})),
        source_module TEXT NOT NULL DEFAULT 'losses' CHECK(trim(source_module) <> ''),
        source_document_type TEXT,
        source_document_id TEXT,
        cutting_scheme_version_id TEXT CHECK(cutting_scheme_version_id IS NULL OR ({UUID_CHECK.format('cutting_scheme_version_id')})),
        inventory_movement_id TEXT,
        requires_inventory_posting INTEGER NOT NULL CHECK(requires_inventory_posting IN (0,1)),
        gross_value TEXT NOT NULL DEFAULT '0' CHECK(trim(gross_value) <> '' AND CAST(gross_value AS NUMERIC) >= 0),
        recoverable_value TEXT NOT NULL DEFAULT '0' CHECK(trim(recoverable_value) <> '' AND CAST(recoverable_value AS NUMERIC) >= 0),
        net_loss_value TEXT NOT NULL DEFAULT '0' CHECK(trim(net_loss_value) <> '' AND CAST(net_loss_value AS NUMERIC) >= 0),
        currency_code TEXT NOT NULL DEFAULT 'MXN' CHECK(length(currency_code)=3),
        notes TEXT NOT NULL DEFAULT '',
        occurred_at TEXT NOT NULL,
        submitted_at TEXT,
        reviewed_at TEXT,
        approved_at TEXT,
        closed_at TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
        FOREIGN KEY(reason_id, classification_id) REFERENCES loss_reasons(id, classification_id),
        CHECK(approved_by_user_id IS NULL OR approved_by_user_id <> reported_by_user_id),
        CHECK(CAST(recoverable_value AS NUMERIC) <= CAST(gross_value AS NUMERIC)),
        CHECK(CAST(net_loss_value AS NUMERIC) = CAST(gross_value AS NUMERIC) - CAST(recoverable_value AS NUMERIC))
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_lines (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        product_id TEXT NOT NULL CHECK({UUID_CHECK.format('product_id')}),
        lot_id TEXT CHECK(lot_id IS NULL OR ({UUID_CHECK.format('lot_id')})),
        location_id TEXT CHECK(location_id IS NULL OR ({UUID_CHECK.format('location_id')})),
        quantity TEXT NOT NULL DEFAULT '0' CHECK(trim(quantity) <> '' AND CAST(quantity AS NUMERIC) >= 0),
        weight TEXT NOT NULL DEFAULT '0' CHECK(trim(weight) <> '' AND CAST(weight AS NUMERIC) >= 0),
        unit TEXT NOT NULL CHECK(trim(unit) <> ''),
        average_weight TEXT CHECK(average_weight IS NULL OR CAST(average_weight AS NUMERIC) >= 0),
        unit_cost TEXT NOT NULL DEFAULT '0' CHECK(CAST(unit_cost AS NUMERIC) >= 0),
        gross_value TEXT NOT NULL DEFAULT '0' CHECK(CAST(gross_value AS NUMERIC) >= 0),
        recoverable_value TEXT NOT NULL DEFAULT '0' CHECK(CAST(recoverable_value AS NUMERIC) >= 0),
        net_loss_value TEXT NOT NULL DEFAULT '0' CHECK(CAST(net_loss_value AS NUMERIC) >= 0),
        temperature TEXT,
        thermal_state TEXT,
        species_code TEXT,
        cut_code TEXT,
        created_at TEXT NOT NULL,
        CHECK(CAST(quantity AS NUMERIC) > 0 OR CAST(weight AS NUMERIC) > 0),
        CHECK(CAST(recoverable_value AS NUMERIC) <= CAST(gross_value AS NUMERIC)),
        CHECK(CAST(net_loss_value AS NUMERIC) = CAST(gross_value AS NUMERIC) - CAST(recoverable_value AS NUMERIC))
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_evidence (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        evidence_type TEXT NOT NULL CHECK(trim(evidence_type) <> ''),
        storage_uri TEXT NOT NULL CHECK(trim(storage_uri) <> ''),
        checksum TEXT NOT NULL CHECK(trim(checksum) <> ''),
        captured_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('captured_by_user_id')}),
        captured_at TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{{}}'
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_valuations (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        valuation_version INTEGER NOT NULL CHECK(valuation_version > 0),
        currency_code TEXT NOT NULL CHECK(length(currency_code)=3),
        gross_value TEXT NOT NULL CHECK(CAST(gross_value AS NUMERIC) >= 0),
        recovered_value TEXT NOT NULL CHECK(CAST(recovered_value AS NUMERIC) >= 0),
        net_loss_value TEXT NOT NULL CHECK(CAST(net_loss_value AS NUMERIC) >= 0),
        valued_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('valued_by_user_id')}),
        valued_at TEXT NOT NULL,
        CHECK(CAST(recovered_value AS NUMERIC) <= CAST(gross_value AS NUMERIC)),
        CHECK(CAST(net_loss_value AS NUMERIC) = CAST(gross_value AS NUMERIC)-CAST(recovered_value AS NUMERIC)),
        UNIQUE(loss_case_id,valuation_version)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_cost_references (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        valuation_id TEXT NOT NULL REFERENCES loss_valuations(id) ON DELETE CASCADE,
        loss_line_id TEXT NOT NULL REFERENCES loss_lines(id),
        reference_type TEXT NOT NULL CHECK(reference_type IN ('INVENTORY_AVERAGE','LOT_RECEIPT','PURCHASE_RECEIPT','MANUAL_AUTHORIZED')),
        reference_id TEXT NOT NULL CHECK({UUID_CHECK.format('reference_id')}),
        cost_basis TEXT NOT NULL CHECK(cost_basis IN ('QUANTITY','WEIGHT')),
        basis_amount TEXT NOT NULL CHECK(CAST(basis_amount AS NUMERIC)>0),
        unit_cost TEXT NOT NULL CHECK(CAST(unit_cost AS NUMERIC)>=0),
        gross_value TEXT NOT NULL CHECK(CAST(gross_value AS NUMERIC)>=0),
        UNIQUE(valuation_id,loss_line_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_approvals (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        requested_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('requested_by_user_id')}),
        authorized_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('authorized_by_user_id')}),
        permission_code TEXT NOT NULL CHECK(trim(permission_code) <> ''),
        decision TEXT NOT NULL CHECK(decision IN ('APPROVED','REJECTED')),
        value_reference TEXT NOT NULL CHECK(CAST(value_reference AS NUMERIC) >= 0),
        approval_limit TEXT NOT NULL CHECK(CAST(approval_limit AS NUMERIC) >= 0),
        reason TEXT NOT NULL CHECK(trim(reason) <> ''),
        decided_at TEXT NOT NULL,
        CHECK(requested_by_user_id <> authorized_by_user_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_dispositions (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id),
        quarantine_id TEXT NOT NULL REFERENCES inventory_quarantine(id),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        authorization_operation_id TEXT UNIQUE CHECK(authorization_operation_id IS NULL OR ({UUID_CHECK.format('authorization_operation_id')})),
        completion_operation_id TEXT UNIQUE CHECK(completion_operation_id IS NULL OR ({UUID_CHECK.format('completion_operation_id')})),
        method_code TEXT NOT NULL CHECK(trim(method_code) <> ''),
        status TEXT NOT NULL CHECK(status IN ('PLANNED','AUTHORIZED','COMPLETED','CANCELLED')),
        quantity TEXT NOT NULL DEFAULT '0' CHECK(CAST(quantity AS NUMERIC) >= 0),
        weight TEXT NOT NULL DEFAULT '0' CHECK(CAST(weight AS NUMERIC) >= 0),
        planned_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('planned_by_user_id')}),
        reason TEXT NOT NULL CHECK(trim(reason) <> ''),
        certificate_required INTEGER NOT NULL CHECK(certificate_required IN (0,1)),
        authorized_by_user_id TEXT CHECK(authorized_by_user_id IS NULL OR ({UUID_CHECK.format('authorized_by_user_id')})),
        authorization_reason TEXT,
        authorized_at TEXT,
        completed_by_user_id TEXT CHECK(completed_by_user_id IS NULL OR ({UUID_CHECK.format('completed_by_user_id')})),
        completed_at TEXT,
        certificate_reference TEXT,
        created_at TEXT NOT NULL,
        CHECK(CAST(quantity AS NUMERIC) > 0 OR CAST(weight AS NUMERIC) > 0),
        CHECK(authorized_by_user_id IS NULL OR authorized_by_user_id <> planned_by_user_id),
        CHECK(completed_by_user_id IS NULL OR completed_by_user_id <> authorized_by_user_id),
        CHECK(status = 'PLANNED' OR authorized_by_user_id IS NOT NULL),
        CHECK(status <> 'COMPLETED' OR completed_by_user_id IS NOT NULL),
        CHECK(status <> 'COMPLETED' OR certificate_required = 0 OR trim(certificate_reference) <> '')
    )""",
    """CREATE TABLE IF NOT EXISTS loss_disposition_evidence (
        disposition_id TEXT NOT NULL REFERENCES loss_dispositions(id) ON DELETE CASCADE,
        evidence_id TEXT NOT NULL REFERENCES loss_evidence(id),
        phase TEXT NOT NULL CHECK(phase IN ('PLANNING','COMPLETION')),
        PRIMARY KEY(disposition_id,evidence_id,phase)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_recoveries (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        recovery_type TEXT NOT NULL CHECK(recovery_type IN ('REWORK','RECLASSIFICATION','CLAIM','BY_PRODUCT','CO_PRODUCT','OTHER')),
        quantity TEXT NOT NULL DEFAULT '0' CHECK(CAST(quantity AS NUMERIC) >= 0),
        weight TEXT NOT NULL DEFAULT '0' CHECK(CAST(weight AS NUMERIC) >= 0),
        recovered_value TEXT NOT NULL DEFAULT '0' CHECK(CAST(recovered_value AS NUMERIC) >= 0),
        reference_id TEXT CHECK(reference_id IS NULL OR ({UUID_CHECK.format('reference_id')})),
        target_product_id TEXT CHECK(target_product_id IS NULL OR ({UUID_CHECK.format('target_product_id')})),
        status TEXT NOT NULL DEFAULT 'APPROVED' CHECK(status IN ('PENDING_APPROVAL','APPROVED','REJECTED','CANCELLED')),
        notes TEXT NOT NULL DEFAULT '',
        recorded_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('recorded_by_user_id')}),
        recorded_at TEXT NOT NULL,
        approved_by_user_id TEXT CHECK(approved_by_user_id IS NULL OR ({UUID_CHECK.format('approved_by_user_id')})),
        approved_at TEXT,
        approval_reason TEXT,
        CHECK(approved_by_user_id IS NULL OR approved_by_user_id <> recorded_by_user_id),
        CHECK(recovery_type NOT IN ('RECLASSIFICATION','BY_PRODUCT','CO_PRODUCT')
              OR (reference_id IS NOT NULL AND target_product_id IS NOT NULL)),
        CHECK(recovery_type <> 'CLAIM' OR reference_id IS NOT NULL)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_lot_risk_assessments (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        lot_id TEXT NOT NULL REFERENCES inventory_lots(id),
        product_id TEXT NOT NULL CHECK({UUID_CHECK.format('product_id')}),
        branch_id TEXT NOT NULL CHECK({UUID_CHECK.format('branch_id')}),
        warehouse_id TEXT NOT NULL CHECK({UUID_CHECK.format('warehouse_id')}),
        risk_level TEXT NOT NULL CHECK(risk_level IN ('NORMAL','WARNING','HIGH','CRITICAL')),
        expiry_risk TEXT NOT NULL CHECK(expiry_risk IN ('NOT_APPLICABLE','OK','WARNING','CRITICAL','EXPIRED')),
        damage_severity TEXT NOT NULL CHECK(damage_severity IN ('NONE','MINOR','MAJOR','UNSAFE')),
        expiration_date TEXT,
        days_to_expiry INTEGER,
        quantity TEXT NOT NULL DEFAULT '0' CHECK(CAST(quantity AS NUMERIC) >= 0),
        weight TEXT NOT NULL DEFAULT '0' CHECK(CAST(weight AS NUMERIC) >= 0),
        quarantine_id TEXT REFERENCES inventory_quarantine(id),
        assessed_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('assessed_by_user_id')}),
        assessed_at TEXT NOT NULL,
        CHECK(CAST(quantity AS NUMERIC) > 0 OR CAST(weight AS NUMERIC) > 0)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_quality_assessments (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        lot_id TEXT NOT NULL REFERENCES inventory_lots(id),
        decision TEXT NOT NULL CHECK(decision IN ('REJECT','CONDEMN')),
        contamination_level TEXT NOT NULL CHECK(contamination_level IN ('NONE','SUSPECTED','CONFIRMED')),
        temperature TEXT,
        minimum_temperature TEXT,
        maximum_temperature TEXT,
        temperature_out_of_range INTEGER NOT NULL DEFAULT 0 CHECK(temperature_out_of_range IN (0,1)),
        temperature_reading_id TEXT REFERENCES inventory_temperature_readings(id),
        quarantine_id TEXT NOT NULL REFERENCES inventory_quarantine(id),
        disposition_id TEXT REFERENCES loss_dispositions(id),
        notes TEXT NOT NULL CHECK(trim(notes) <> ''),
        decided_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('decided_by_user_id')}),
        decided_at TEXT NOT NULL,
        CHECK((temperature IS NULL AND minimum_temperature IS NULL AND maximum_temperature IS NULL)
           OR (temperature IS NOT NULL AND minimum_temperature IS NOT NULL AND maximum_temperature IS NOT NULL)),
        CHECK(minimum_temperature IS NULL OR CAST(minimum_temperature AS NUMERIC) <= CAST(maximum_temperature AS NUMERIC)),
        CHECK(decision <> 'CONDEMN' OR contamination_level='CONFIRMED' OR temperature_out_of_range=1)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_quality_evidence (
        quality_assessment_id TEXT NOT NULL REFERENCES loss_quality_assessments(id) ON DELETE CASCADE,
        evidence_id TEXT NOT NULL REFERENCES loss_evidence(id) ON DELETE CASCADE,
        PRIMARY KEY(quality_assessment_id, evidence_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_transfer_links (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL UNIQUE REFERENCES loss_cases(id) ON DELETE CASCADE,
        transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        difference_id TEXT NOT NULL UNIQUE REFERENCES transfer_differences(id),
        resolution_id TEXT NOT NULL UNIQUE REFERENCES transfer_difference_resolutions(id),
        receipt_id TEXT NOT NULL REFERENCES transfer_receipts(id),
        receipt_operation_id TEXT NOT NULL CHECK({UUID_CHECK.format('receipt_operation_id')}),
        difference_type TEXT NOT NULL CHECK(trim(difference_type) <> ''),
        responsible_stage TEXT NOT NULL CHECK(trim(responsible_stage) <> ''),
        suggested_party_type TEXT NOT NULL CHECK(suggested_party_type IN
            ('CARRIER','ORIGIN_BRANCH','DESTINATION_BRANCH','EMPLOYEE','SUPPLIER','OTHER')),
        inventory_effect TEXT NOT NULL CHECK(inventory_effect='POSTED_BY_TRANSFER_RECEIPT'),
        created_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_transfer_claims (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        transfer_id TEXT NOT NULL REFERENCES stock_transfers(id),
        party_type TEXT NOT NULL CHECK(party_type IN
            ('CARRIER','ORIGIN_BRANCH','DESTINATION_BRANCH','EMPLOYEE','SUPPLIER','OTHER')),
        responsible_party_id TEXT CHECK(responsible_party_id IS NULL OR ({UUID_CHECK.format('responsible_party_id')})),
        claimed_value TEXT NOT NULL CHECK(CAST(claimed_value AS NUMERIC)>0),
        status TEXT NOT NULL CHECK(status IN ('OPEN','SUBMITTED','ACCEPTED','REJECTED','PAID','CANCELLED')),
        reason TEXT NOT NULL CHECK(trim(reason) <> ''),
        evidence_json TEXT NOT NULL DEFAULT '[]',
        created_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('created_by_user_id')}),
        created_at TEXT NOT NULL,
        resolved_by_user_id TEXT CHECK(resolved_by_user_id IS NULL OR ({UUID_CHECK.format('resolved_by_user_id')})),
        resolved_at TEXT,
        resolution_notes TEXT,
        CHECK(party_type='OTHER' OR responsible_party_id IS NOT NULL)
    )""",
    f"""CREATE TABLE IF NOT EXISTS yield_variances (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT REFERENCES loss_cases(id),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        product_id TEXT NOT NULL CHECK({UUID_CHECK.format('product_id')}),
        production_order_id TEXT NOT NULL CHECK({UUID_CHECK.format('production_order_id')}),
        yield_profile_version_id TEXT NOT NULL CHECK({UUID_CHECK.format('yield_profile_version_id')}),
        expected_output TEXT NOT NULL CHECK(CAST(expected_output AS NUMERIC) >= 0),
        actual_output TEXT NOT NULL CHECK(CAST(actual_output AS NUMERIC) >= 0),
        variance_quantity TEXT NOT NULL,
        variance_rate TEXT NOT NULL,
        severity TEXT NOT NULL CHECK(severity IN ('NORMAL','WARNING','OUT_OF_TOLERANCE','CRITICAL')),
        detected_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_meat_output_observations (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        yield_variance_id TEXT NOT NULL REFERENCES yield_variances(id) ON DELETE CASCADE,
        production_id TEXT NOT NULL CHECK({UUID_CHECK.format('production_id')}),
        product_id TEXT NOT NULL CHECK({UUID_CHECK.format('product_id')}),
        species_id TEXT NOT NULL CHECK({UUID_CHECK.format('species_id')}),
        cut_classification_id TEXT CHECK(cut_classification_id IS NULL OR ({UUID_CHECK.format('cut_classification_id')})),
        lot_id TEXT CHECK(lot_id IS NULL OR ({UUID_CHECK.format('lot_id')})),
        output_type TEXT NOT NULL CHECK(output_type IN ('MAIN_PRODUCT','CO_PRODUCT','BY_PRODUCT','WASTE','LOSS')),
        measure_kind TEXT NOT NULL CHECK(measure_kind IN ('BY_PIECE','BY_WEIGHT')),
        quantity TEXT NOT NULL DEFAULT '0' CHECK(CAST(quantity AS NUMERIC) >= 0),
        weight TEXT NOT NULL DEFAULT '0' CHECK(CAST(weight AS NUMERIC) >= 0),
        created_at TEXT NOT NULL,
        CHECK(CAST(quantity AS NUMERIC) > 0 OR CAST(weight AS NUMERIC) > 0)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_yield_alerts (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        yield_variance_id TEXT NOT NULL UNIQUE REFERENCES yield_variances(id) ON DELETE CASCADE,
        loss_case_id TEXT REFERENCES loss_cases(id),
        severity TEXT NOT NULL CHECK(severity IN ('WARNING','OUT_OF_TOLERANCE','CRITICAL')),
        expected_yield_pct TEXT NOT NULL,
        actual_yield_pct TEXT NOT NULL,
        variance_pct TEXT NOT NULL,
        lower_tolerance_pct TEXT NOT NULL,
        upper_tolerance_pct TEXT NOT NULL,
        message TEXT NOT NULL CHECK(trim(message) <> ''),
        status TEXT NOT NULL DEFAULT 'OPEN' CHECK(status IN ('OPEN','ACKNOWLEDGED','RESOLVED')),
        created_at TEXT NOT NULL,
        acknowledged_at TEXT,
        resolved_at TEXT
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_investigations (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT NOT NULL UNIQUE REFERENCES loss_cases(id),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        conclusion_operation_id TEXT UNIQUE CHECK(conclusion_operation_id IS NULL OR ({UUID_CHECK.format('conclusion_operation_id')})),
        status TEXT NOT NULL CHECK(status IN ('OPEN','IN_PROGRESS','CONCLUDED','CANCELLED')),
        opened_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('opened_by_user_id')}),
        assigned_to_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('assigned_to_user_id')}),
        opening_reason TEXT NOT NULL CHECK(trim(opening_reason) <> ''),
        findings TEXT NOT NULL DEFAULT '',
        conclusion TEXT NOT NULL DEFAULT '',
        opened_at TEXT NOT NULL,
        due_at TEXT,
        concluded_by_user_id TEXT CHECK(concluded_by_user_id IS NULL OR ({UUID_CHECK.format('concluded_by_user_id')})),
        concluded_at TEXT,
        CHECK(concluded_by_user_id IS NULL OR concluded_by_user_id <> opened_by_user_id),
        CHECK(status <> 'CONCLUDED' OR (concluded_by_user_id IS NOT NULL AND trim(conclusion) <> ''))
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_investigation_findings (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        investigation_id TEXT NOT NULL REFERENCES loss_investigations(id) ON DELETE CASCADE,
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        cause_code TEXT NOT NULL CHECK(trim(cause_code) <> ''),
        description TEXT NOT NULL CHECK(trim(description) <> ''),
        is_primary INTEGER NOT NULL DEFAULT 0 CHECK(is_primary IN (0,1)),
        recorded_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('recorded_by_user_id')}),
        recorded_at TEXT NOT NULL,
        UNIQUE(investigation_id,cause_code,description)
    )""",
    """CREATE TABLE IF NOT EXISTS loss_investigation_evidence (
        investigation_id TEXT NOT NULL REFERENCES loss_investigations(id) ON DELETE CASCADE,
        evidence_id TEXT NOT NULL REFERENCES loss_evidence(id),
        finding_id TEXT REFERENCES loss_investigation_findings(id) ON DELETE CASCADE,
        phase TEXT NOT NULL CHECK(phase IN ('INVESTIGATION','FINDING','CONCLUSION')),
        CHECK((phase = 'FINDING') = (finding_id IS NOT NULL)),
        UNIQUE(investigation_id,evidence_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_root_cause_catalog (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        code TEXT NOT NULL UNIQUE CHECK(trim(code) <> ''),
        category TEXT NOT NULL CHECK(category IN ('PEOPLE','PROCESS','EQUIPMENT','MATERIAL','ENVIRONMENT','MANAGEMENT','OTHER')),
        display_name TEXT NOT NULL CHECK(trim(display_name) <> ''),
        description TEXT NOT NULL DEFAULT '',
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        version INTEGER NOT NULL DEFAULT 0 CHECK(version >= 0),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_root_cause_analyses (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        investigation_id TEXT NOT NULL UNIQUE REFERENCES loss_investigations(id) ON DELETE CASCADE,
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        method TEXT NOT NULL CHECK(method IN ('FIVE_WHYS','FISHBONE','PARETO','FAULT_TREE','DIRECT_OBSERVATION')),
        summary TEXT NOT NULL CHECK(trim(summary) <> ''),
        recorded_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('recorded_by_user_id')}),
        recorded_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_root_causes (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        analysis_id TEXT NOT NULL REFERENCES loss_root_cause_analyses(id) ON DELETE CASCADE,
        catalog_entry_id TEXT NOT NULL REFERENCES loss_root_cause_catalog(id),
        role TEXT NOT NULL CHECK(role IN ('PRIMARY','CONTRIBUTING')),
        rationale TEXT NOT NULL CHECK(trim(rationale) <> ''),
        recorded_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('recorded_by_user_id')}),
        recorded_at TEXT NOT NULL,
        UNIQUE(analysis_id,catalog_entry_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_corrective_actions (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        investigation_id TEXT NOT NULL REFERENCES loss_investigations(id),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        submission_operation_id TEXT UNIQUE CHECK(submission_operation_id IS NULL OR ({UUID_CHECK.format('submission_operation_id')})),
        verification_operation_id TEXT UNIQUE CHECK(verification_operation_id IS NULL OR ({UUID_CHECK.format('verification_operation_id')})),
        title TEXT NOT NULL CHECK(trim(title) <> ''),
        description TEXT NOT NULL,
        created_by_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('created_by_user_id')}),
        owner_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('owner_user_id')}),
        status TEXT NOT NULL CHECK(status IN ('OPEN','IN_PROGRESS','PENDING_VERIFICATION','EFFECTIVE','INEFFECTIVE','CANCELLED')),
        due_at TEXT NOT NULL,
        completion_notes TEXT,
        completion_evidence_uri TEXT,
        completion_evidence_checksum TEXT,
        submitted_at TEXT,
        verified_by_user_id TEXT CHECK(verified_by_user_id IS NULL OR ({UUID_CHECK.format('verified_by_user_id')})),
        verified_at TEXT,
        effectiveness_notes TEXT,
        created_at TEXT NOT NULL,
        CHECK(status NOT IN ('PENDING_VERIFICATION','EFFECTIVE','INEFFECTIVE') OR submitted_at IS NOT NULL),
        CHECK(status NOT IN ('EFFECTIVE','INEFFECTIVE') OR verified_by_user_id IS NOT NULL),
        CHECK(verified_by_user_id IS NULL OR (verified_by_user_id <> owner_user_id AND verified_by_user_id <> created_by_user_id))
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_corrective_action_tasks (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        corrective_action_id TEXT NOT NULL REFERENCES loss_corrective_actions(id) ON DELETE CASCADE,
        title TEXT NOT NULL CHECK(trim(title) <> ''),
        assigned_to_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('assigned_to_user_id')}),
        status TEXT NOT NULL CHECK(status IN ('OPEN','IN_PROGRESS','COMPLETED','CANCELLED')),
        due_at TEXT,
        completed_at TEXT,
        created_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_audit_log (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        loss_case_id TEXT REFERENCES loss_cases(id),
        operation_id TEXT NOT NULL CHECK({UUID_CHECK.format('operation_id')}),
        actor_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('actor_user_id')}),
        branch_id TEXT NOT NULL CHECK({UUID_CHECK.format('branch_id')}),
        warehouse_id TEXT,
        action TEXT NOT NULL CHECK(trim(action) <> ''),
        before_json TEXT,
        after_json TEXT,
        reason TEXT NOT NULL DEFAULT '',
        occurred_at TEXT NOT NULL,
        correlation_id TEXT NOT NULL CHECK({UUID_CHECK.format('correlation_id')})
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_notification_subscriptions (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        user_id TEXT NOT NULL CHECK({UUID_CHECK.format('user_id')}),
        branch_id TEXT NOT NULL CHECK({UUID_CHECK.format('branch_id')}),
        role_code TEXT NOT NULL CHECK(trim(role_code)<>''),
        phone_e164 TEXT CHECK(phone_e164 IS NULL OR (substr(phone_e164,1,1)='+' AND length(phone_e164) BETWEEN 9 AND 16)),
        in_app_enabled INTEGER NOT NULL DEFAULT 1 CHECK(in_app_enabled IN (0,1)),
        whatsapp_enabled INTEGER NOT NULL DEFAULT 0 CHECK(whatsapp_enabled IN (0,1)),
        active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)),
        created_at TEXT NOT NULL,
        UNIQUE(user_id,branch_id,role_code)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_notification_deliveries (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        source_event_id TEXT NOT NULL CHECK({UUID_CHECK.format('source_event_id')}),
        routing_operation_id TEXT NOT NULL CHECK({UUID_CHECK.format('routing_operation_id')}),
        loss_case_id TEXT NOT NULL REFERENCES loss_cases(id) ON DELETE CASCADE,
        recipient_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('recipient_user_id')}),
        channel TEXT NOT NULL CHECK(channel IN ('IN_APP','WHATSAPP')),
        severity TEXT NOT NULL CHECK(severity IN ('ACTION_REQUIRED','CRITICAL')),
        message TEXT NOT NULL CHECK(trim(message)<>''),
        phone_e164 TEXT,
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','SENT','FAILED')),
        provider_message_id TEXT,
        last_error TEXT,
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count>=0),
        created_at TEXT NOT NULL,
        sent_at TEXT,
        UNIQUE(source_event_id,recipient_user_id,channel)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_notification_audit (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        delivery_id TEXT NOT NULL REFERENCES loss_notification_deliveries(id) ON DELETE CASCADE,
        attempt_number INTEGER NOT NULL CHECK(attempt_number>0),
        status TEXT NOT NULL CHECK(status IN ('SENT','FAILED')),
        provider_message_id TEXT,
        error TEXT,
        occurred_at TEXT NOT NULL,
        UNIQUE(delivery_id,attempt_number)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_outbox (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        event_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('event_id')}),
        event_name TEXT NOT NULL CHECK(trim(event_name) <> ''),
        aggregate_id TEXT NOT NULL CHECK({UUID_CHECK.format('aggregate_id')}),
        operation_id TEXT NOT NULL CHECK({UUID_CHECK.format('operation_id')}),
        causation_id TEXT,
        correlation_id TEXT NOT NULL CHECK({UUID_CHECK.format('correlation_id')}),
        payload_json TEXT NOT NULL CHECK(trim(payload_json) <> ''),
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','PROCESSING','DISPATCHED','FAILED','DEAD_LETTER')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
        created_at TEXT NOT NULL,
        next_attempt_at TEXT,
        dispatched_at TEXT,
        last_error TEXT,
        CHECK(event_id <> operation_id AND event_id <> aggregate_id AND operation_id <> aggregate_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_processed_operations (
        operation_id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('operation_id')}),
        operation_type TEXT NOT NULL CHECK(trim(operation_type) <> ''),
        result_entity_id TEXT NOT NULL CHECK({UUID_CHECK.format('result_entity_id')}),
        result_json TEXT NOT NULL,
        processed_at TEXT NOT NULL,
        CHECK(operation_id <> result_entity_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_offline_drafts (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        device_id TEXT NOT NULL CHECK({UUID_CHECK.format('device_id')}),
        branch_id TEXT NOT NULL CHECK({UUID_CHECK.format('branch_id')}),
        warehouse_id TEXT NOT NULL CHECK({UUID_CHECK.format('warehouse_id')}),
        actor_user_id TEXT NOT NULL CHECK({UUID_CHECK.format('actor_user_id')}),
        payload_json TEXT NOT NULL CHECK(trim(payload_json) <> ''),
        status TEXT NOT NULL DEFAULT 'DRAFT' CHECK(status IN ('DRAFT','QUEUED','SYNCED','CONFLICT')),
        remote_revision TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        CHECK(id <> operation_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_offline_evidence (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        draft_id TEXT NOT NULL REFERENCES loss_offline_drafts(id) ON DELETE CASCADE,
        evidence_type TEXT NOT NULL CHECK(trim(evidence_type) <> ''),
        storage_uri TEXT NOT NULL CHECK(trim(storage_uri) <> ''),
        checksum TEXT NOT NULL CHECK(length(checksum)=64),
        byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
        upload_status TEXT NOT NULL DEFAULT 'PENDING' CHECK(upload_status IN ('PENDING','UPLOADED','FAILED')),
        created_at TEXT NOT NULL
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_sync_outbox (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        draft_id TEXT NOT NULL REFERENCES loss_offline_drafts(id) ON DELETE CASCADE,
        operation_id TEXT NOT NULL UNIQUE CHECK({UUID_CHECK.format('operation_id')}),
        device_id TEXT NOT NULL CHECK({UUID_CHECK.format('device_id')}),
        branch_id TEXT NOT NULL CHECK({UUID_CHECK.format('branch_id')}),
        local_sequence INTEGER NOT NULL CHECK(local_sequence > 0),
        base_revision TEXT NOT NULL DEFAULT '',
        payload_json TEXT NOT NULL CHECK(trim(payload_json) <> ''),
        payload_hash TEXT NOT NULL CHECK(length(payload_hash)=64),
        status TEXT NOT NULL DEFAULT 'PENDING' CHECK(status IN ('PENDING','RETRY','SYNCED','CONFLICT')),
        attempt_count INTEGER NOT NULL DEFAULT 0 CHECK(attempt_count >= 0),
        last_error TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE(device_id,local_sequence),
        CHECK(id <> operation_id AND id <> draft_id)
    )""",
    f"""CREATE TABLE IF NOT EXISTS loss_sync_conflicts (
        id TEXT NOT NULL PRIMARY KEY CHECK({UUID_CHECK.format('id')}),
        envelope_id TEXT NOT NULL UNIQUE REFERENCES loss_sync_outbox(id) ON DELETE CASCADE,
        conflict_type TEXT NOT NULL CHECK(trim(conflict_type) <> ''),
        remote_revision TEXT NOT NULL DEFAULT '',
        remote_payload_json TEXT NOT NULL DEFAULT '{{}}',
        resolution TEXT NOT NULL DEFAULT 'PENDING' CHECK(resolution IN ('PENDING','KEEP_LOCAL','ACCEPT_REMOTE','MANUAL_MERGE')),
        detected_at TEXT NOT NULL,
        resolved_at TEXT
    )""",
)


INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_loss_cases_scope_status ON loss_cases(branch_id, warehouse_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loss_cases_classification_date ON loss_cases(classification_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_cases_reason_date ON loss_cases(reason_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_cases_source ON loss_cases(source_module, source_document_type, source_document_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_lines_case ON loss_lines(loss_case_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_lines_product_lot ON loss_lines(product_id, lot_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_evidence_case ON loss_evidence(loss_case_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_approvals_case ON loss_approvals(loss_case_id, decided_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_dispositions_case_status ON loss_dispositions(loss_case_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loss_valuations_case_version ON loss_valuations(loss_case_id,valuation_version)",
    "CREATE INDEX IF NOT EXISTS idx_loss_cost_references_source ON loss_cost_references(reference_type,reference_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_dispositions_quarantine_status ON loss_dispositions(quarantine_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_loss_disposition_evidence_phase ON loss_disposition_evidence(disposition_id, phase)",
    "CREATE INDEX IF NOT EXISTS idx_loss_recoveries_case ON loss_recoveries(loss_case_id, recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_recoveries_pending ON loss_recoveries(status, recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_lot_risk_case_lot ON loss_lot_risk_assessments(loss_case_id, lot_id, assessed_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_lot_risk_priority ON loss_lot_risk_assessments(branch_id, risk_level, assessed_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_loss_lot_active_quarantine ON loss_lot_risk_assessments(loss_case_id, lot_id) WHERE quarantine_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_loss_quality_case_lot ON loss_quality_assessments(loss_case_id, lot_id, decided_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_quality_contamination ON loss_quality_assessments(contamination_level, decision, decided_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_transfer_links_transfer ON loss_transfer_links(transfer_id, responsible_stage)",
    "CREATE INDEX IF NOT EXISTS idx_loss_transfer_claims_status ON loss_transfer_claims(status, party_type, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_yield_variances_product_date ON yield_variances(product_id, detected_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_meat_outputs_variance ON loss_meat_output_observations(yield_variance_id, output_type)",
    "CREATE INDEX IF NOT EXISTS idx_loss_meat_outputs_species_cut ON loss_meat_output_observations(species_id, cut_classification_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_yield_alerts_status_severity ON loss_yield_alerts(status, severity, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_investigations_status_due ON loss_investigations(status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_investigation_findings_case ON loss_investigation_findings(investigation_id, recorded_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_investigation_evidence_phase ON loss_investigation_evidence(investigation_id, phase)",
    "CREATE INDEX IF NOT EXISTS idx_loss_root_cause_catalog_search ON loss_root_cause_catalog(active, category, display_name)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_loss_root_cause_primary ON loss_root_causes(analysis_id) WHERE role='PRIMARY'",
    "CREATE INDEX IF NOT EXISTS idx_loss_corrective_actions_status_due ON loss_corrective_actions(status, due_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_audit_case_time ON loss_audit_log(loss_case_id, occurred_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_audit_operation ON loss_audit_log(operation_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_notification_subscriptions_route ON loss_notification_subscriptions(branch_id,role_code,active)",
    "CREATE INDEX IF NOT EXISTS idx_loss_notification_deliveries_inbox ON loss_notification_deliveries(recipient_user_id,channel,status,created_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_outbox_dispatch ON loss_outbox(status, next_attempt_at, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_outbox_operation ON loss_outbox(operation_id)",
    "CREATE INDEX IF NOT EXISTS idx_loss_offline_drafts_scope ON loss_offline_drafts(branch_id,device_id,status,updated_at)",
    "CREATE INDEX IF NOT EXISTS idx_loss_offline_evidence_draft ON loss_offline_evidence(draft_id,upload_status)",
    "CREATE INDEX IF NOT EXISTS idx_loss_sync_outbox_ready ON loss_sync_outbox(status,device_id,local_sequence)",
    "CREATE INDEX IF NOT EXISTS idx_loss_sync_conflicts_pending ON loss_sync_conflicts(resolution,detected_at)",
)


CLASSIFICATION_NAMES = {
    LossClassificationCode.THEORETICAL_LOSS: "Merma teórica",
    LossClassificationCode.PROCESS_LOSS: "Merma de proceso",
    LossClassificationCode.CUTTING_LOSS: "Merma de corte",
    LossClassificationCode.YIELD_VARIANCE: "Variación de rendimiento",
    LossClassificationCode.HANDLING_DAMAGE: "Daño por manipulación",
    LossClassificationCode.TRANSPORT_DAMAGE: "Daño en transporte",
    LossClassificationCode.TRANSFER_DIFFERENCE: "Diferencia de transferencia",
    LossClassificationCode.RECEIVING_DIFFERENCE: "Diferencia de recepción",
    LossClassificationCode.EXPIRY: "Caducidad",
    LossClassificationCode.SPOILAGE: "Deterioro",
    LossClassificationCode.TEMPERATURE_EXCURSION: "Desviación de temperatura",
    LossClassificationCode.QUALITY_REJECTION: "Rechazo de calidad",
    LossClassificationCode.CONDEMNATION: "Decomiso",
    LossClassificationCode.CONTAMINATION: "Contaminación",
    LossClassificationCode.PACKAGING_FAILURE: "Falla de empaque",
    LossClassificationCode.OVERWEIGHT_GIVEAWAY: "Sobrepeso entregado",
    LossClassificationCode.UNDERWEIGHT_VARIANCE: "Variación por bajo peso",
    LossClassificationCode.COUNT_VARIANCE: "Diferencia de conteo",
    LossClassificationCode.SHRINKAGE: "Pérdida desconocida",
    LossClassificationCode.THEFT_SUSPECTED: "Posible robo",
    LossClassificationCode.QUALITY_SAMPLE: "Muestra de calidad",
    LossClassificationCode.PRODUCTION_SAMPLE: "Muestra de producción",
    LossClassificationCode.CUSTOMER_RETURN_LOSS: "Pérdida por devolución",
    LossClassificationCode.SUPPLIER_REJECTION: "Rechazo a proveedor",
    LossClassificationCode.REWORK_LOSS: "Pérdida de reproceso",
    LossClassificationCode.DISPOSAL_LOSS: "Pérdida de disposición",
    LossClassificationCode.NATURAL_LOSS: "Pérdida natural",
    LossClassificationCode.OTHER_AUTHORIZED: "Otra pérdida autorizada",
}


def _seed_classifications(connection) -> None:
    now = "2026-08-03T00:00:00+00:00"
    for classification in LossClassificationCode:
        connection.execute(
            """INSERT OR IGNORE INTO loss_classifications
               (id, code, display_name, description, active, version, created_at, updated_at)
               VALUES (?,?,?,?,1,1,?,?)""",
            (new_uuid(), classification.value, CLASSIFICATION_NAMES[classification], "", now, now),
        )


def _seed_general_reasons(connection) -> None:
    """Give every clean installation one configurable, non-free-text cause."""
    now = "2026-08-03T00:00:00+00:00"
    rows = connection.execute("SELECT id,code,display_name FROM loss_classifications").fetchall()
    for classification_id, code, display_name in rows:
        connection.execute(
            """INSERT OR IGNORE INTO loss_reasons
               (id,classification_id,code,display_name,description,
                requires_evidence,requires_investigation,active,version,created_at,updated_at)
               VALUES (?,?,?,?,'',0,0,1,1,?,?)""",
            (new_uuid(), classification_id, f"GENERAL_{code}",
             f"Causa general: {display_name}", now, now),
        )


ROOT_CAUSE_CATALOG = (
    ("TRAINING_GAP","PEOPLE","Capacitación insuficiente"),
    ("HUMAN_ERROR","PEOPLE","Error humano"),
    ("PROCEDURE_MISSING","PROCESS","Procedimiento inexistente"),
    ("PROCEDURE_NOT_FOLLOWED","PROCESS","Procedimiento no seguido"),
    ("EQUIPMENT_FAILURE","EQUIPMENT","Falla de equipo"),
    ("MAINTENANCE_GAP","EQUIPMENT","Mantenimiento insuficiente"),
    ("MATERIAL_DEFECT","MATERIAL","Defecto de materia prima"),
    ("SUPPLIER_VARIATION","MATERIAL","Variación de proveedor"),
    ("TEMPERATURE_CONDITION","ENVIRONMENT","Condición de temperatura"),
    ("FACILITY_CONDITION","ENVIRONMENT","Condición de instalaciones"),
    ("SUPERVISION_GAP","MANAGEMENT","Supervisión insuficiente"),
    ("PLANNING_GAP","MANAGEMENT","Planeación insuficiente"),
)


def _seed_root_cause_catalog(connection) -> None:
    now = "2026-08-03T00:00:00+00:00"
    for code,category,name in ROOT_CAUSE_CATALOG:
        connection.execute(
            "INSERT OR IGNORE INTO loss_root_cause_catalog (id,code,category,display_name,description,active,version,created_at,updated_at) VALUES (?,?,?,?,?,1,1,?,?)",
            (new_uuid(),code,category,name,"",now,now))


def run(connection) -> None:
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        for statement in DDL:
            connection.execute(statement)
        for statement in INDEXES:
            connection.execute(statement)
        _seed_classifications(connection)
        _seed_general_reasons(connection)
        _seed_root_cause_catalog(connection)
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(f"LOSS-3 foreign-key violations: {violations}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise


up = run
