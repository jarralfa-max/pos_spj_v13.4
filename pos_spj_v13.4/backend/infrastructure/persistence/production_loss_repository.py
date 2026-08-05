"""Canonical recipe/yield reader and atomic LOSS-7 persistence adapter."""
import json
from datetime import datetime, timezone
from decimal import Decimal

from backend.domain.losses.exceptions import LossInvariantError
from backend.shared.ids import new_uuid


class ProductionLossRepository:
    def __init__(self, connection): self._db = connection

    def find_processed(self, operation_id):
        row = self._db.execute(
            "SELECT result_json FROM loss_processed_operations WHERE operation_id=?",
            (operation_id,)).fetchone()
        if not row: return None
        data = json.loads(row[0])
        return (data.get("normal_case_id"), data.get("abnormal_case_id"),
                Decimal(data["normal_loss_weight"]), Decimal(data["abnormal_loss_weight"]),
                Decimal(data["actual_yield_pct"]), data.get("alert_id"))

    def load_context(self, *, input_product_id, recipe_version_id,
                     yield_profile_version_id, cutting_scheme_version_id=None):
        row = self._db.execute(
            "SELECT yv.tolerance_pct FROM recipe_versions rv "
            "JOIN recipes r ON r.id=rv.recipe_id "
            "JOIN yield_profiles yp ON yp.input_product_id=r.product_id AND yp.active=1 "
            "JOIN yield_profile_versions yv ON yv.yield_profile_id=yp.id "
            "WHERE rv.id=? AND rv.status='ACTIVE' AND r.active=1 AND r.product_id=? "
            "AND yv.id=? AND yv.status='ACTIVE'",
            (recipe_version_id, input_product_id, yield_profile_version_id)).fetchone()
        if not row: return None
        outputs = self._db.execute(
            "SELECT product_id,output_type,expected_yield_pct,minimum_yield_pct,maximum_yield_pct FROM yield_outputs "
            "WHERE version_id=? ORDER BY sequence,id", (yield_profile_version_id,)).fetchall()
        productive = [r for r in outputs if r[1] not in ("WASTE", "LOSS")]
        if not productive:
            raise LossInvariantError("El perfil activo no tiene outputs productivos")
        expected = sum((Decimal(str(r[2])) for r in productive), Decimal("0"))
        minimum = (sum((Decimal(str(r[3])) for r in productive), Decimal("0"))
                   if all(r[3] is not None for r in productive) else None)
        maximum = (sum((Decimal(str(r[4])) for r in productive), Decimal("0"))
                   if all(r[4] is not None for r in productive) else None)
        primary = next((str(r[0]) for r in productive if r[1] == "MAIN_PRODUCT"),
                       str(productive[0][0]))
        normal = self._reason("PROCESS_LOSS")
        abnormal = self._reason("YIELD_VARIANCE")
        if not normal or not abnormal:
            raise LossInvariantError("Faltan causas activas para pérdidas de producción")
        return {"expected_yield_pct": expected, "tolerance_pct": Decimal(str(row[0])),
                "minimum_yield_pct": minimum, "maximum_yield_pct": maximum,
                "normal_classification_id": normal[0], "normal_reason_id": normal[1],
                "abnormal_classification_id": abnormal[0], "abnormal_reason_id": abnormal[1],
                "primary_output_product_id": primary,
                "output_product_ids": frozenset(str(r[0]) for r in outputs),
                "meat_output_config": self._load_cutting_context(
                    input_product_id, cutting_scheme_version_id)
                    if cutting_scheme_version_id else None}

    def _load_cutting_context(self, input_product_id, version_id):
        scheme = self._db.execute(
            "SELECT cs.species_id FROM cutting_scheme_versions csv "
            "JOIN cutting_schemes cs ON cs.id=csv.cutting_scheme_id "
            "JOIN products p ON p.id=cs.input_product_id "
            "WHERE csv.id=? AND csv.status='ACTIVE' AND cs.active=1 "
            "AND cs.input_product_id=? AND p.species_id=cs.species_id",
            (version_id, input_product_id)).fetchone()
        if not scheme:
            raise LossInvariantError("Esquema de despiece activo no encontrado para la especie")
        species_id = str(scheme[0])
        rows = self._db.execute(
            "SELECT co.product_id,co.output_type,co.measure_kind,co.cut_classification_id "
            "FROM cutting_outputs co JOIN products p ON p.id=co.product_id "
            "LEFT JOIN cut_classifications cc ON cc.id=co.cut_classification_id "
            "WHERE co.version_id=? AND p.species_id=? "
            "AND (co.cut_classification_id IS NULL OR cc.species_id=?)",
            (version_id, species_id, species_id)).fetchall()
        if not rows:
            raise LossInvariantError("El despiece activo no tiene salidas cárnicas válidas")
        return {str(r[0]): {"species_id": species_id, "output_type": str(r[1]),
                            "measure_kind": str(r[2]),
                            "cut_classification_id": r[3]} for r in rows}

    def _reason(self, classification_code):
        return self._db.execute(
            "SELECT c.id,r.id FROM loss_classifications c JOIN loss_reasons r "
            "ON r.classification_id=c.id WHERE c.code=? AND c.active=1 AND r.active=1 "
            "ORDER BY r.code LIMIT 1", (classification_code,)).fetchone()

    def save_analysis(self, *, operation_id, production_id, recipe_version_id,
                      yield_profile_version_id, cutting_scheme_version_id,
                      primary_output_product_id, normal_case, abnormal_case,
                      analysis, alert, outputs, events):
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute("SAVEPOINT loss7_production")
        try:
            for case in (normal_case, abnormal_case):
                if case: self._insert_case(case, now)
            linked_case = abnormal_case or normal_case
            variance_id = new_uuid()
            self._db.execute(
                "INSERT INTO yield_variances (id,loss_case_id,operation_id,product_id,"
                "production_order_id,yield_profile_version_id,expected_output,actual_output,"
                "variance_quantity,variance_rate,severity,detected_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (variance_id, linked_case.id if linked_case else None, operation_id,
                 primary_output_product_id, production_id, yield_profile_version_id,
                 str(analysis.expected_output_weight), str(analysis.actual_output_weight),
                 str(analysis.variance_weight), str(analysis.variance_pct),
                 analysis.severity, now))
            if alert:
                self._db.execute(
                    "INSERT INTO loss_yield_alerts (id,yield_variance_id,loss_case_id,"
                    "severity,expected_yield_pct,actual_yield_pct,variance_pct,"
                    "lower_tolerance_pct,upper_tolerance_pct,message,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (alert.id, variance_id, linked_case.id if linked_case else None,
                     alert.severity, str(analysis.expected_yield_pct),
                     str(analysis.actual_yield_pct), str(analysis.variance_pct),
                     str(analysis.lower_tolerance_pct), str(analysis.upper_tolerance_pct),
                     alert.message, now))
            for output in outputs:
                if output.species_id is None:
                    continue
                self._db.execute(
                    "INSERT INTO loss_meat_output_observations (id,yield_variance_id,"
                    "production_id,product_id,species_id,cut_classification_id,lot_id,"
                    "output_type,measure_kind,quantity,weight,created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_uuid(), variance_id, production_id, output.product_id,
                     output.species_id, output.cut_classification_id, output.lot_id,
                     output.output_type.value, output.measure_kind.value,
                     str(output.quantity), str(output.weight), now))
            for event in events:
                self._db.execute(
                    "INSERT INTO loss_outbox (id,event_id,event_name,aggregate_id,operation_id,"
                    "correlation_id,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (new_uuid(), event["event_id"], event["event_name"], event["entity_id"],
                     operation_id, event["event_id"],
                     json.dumps(event, ensure_ascii=False, sort_keys=True), now))
            data = {"normal_case_id": normal_case.id if normal_case else None,
                    "abnormal_case_id": abnormal_case.id if abnormal_case else None,
                    "normal_loss_weight": str(analysis.normal_loss_weight),
                    "abnormal_loss_weight": str(analysis.abnormal_loss_weight),
                    "actual_yield_pct": str(analysis.actual_yield_pct),
                    "alert_id": alert.id if alert else None,
                    "recipe_version_id": recipe_version_id,
                    "yield_profile_version_id": yield_profile_version_id}
            data["cutting_scheme_version_id"] = cutting_scheme_version_id
            self._db.execute(
                "INSERT INTO loss_processed_operations (operation_id,operation_type,"
                "result_entity_id,result_json,processed_at) VALUES (?,?,?,?,?)",
                (operation_id, "ANALYZE_PRODUCTION_LOSS", variance_id,
                 json.dumps(data, sort_keys=True), now))
            self._db.execute("RELEASE SAVEPOINT loss7_production")
        except Exception:
            self._db.execute("ROLLBACK TO SAVEPOINT loss7_production")
            self._db.execute("RELEASE SAVEPOINT loss7_production")
            raise

    def _insert_case(self, case, now):
        classification_id = self._db.execute(
            "SELECT id FROM loss_classifications WHERE code=? AND active=1",
            (case.classification.value,)).fetchone()[0]
        self._db.execute(
            "INSERT INTO loss_cases (id,operation_id,branch_id,warehouse_id,reported_by_user_id,"
            "classification_id,reason_id,origin,status,source_module,source_document_type,"
            "source_document_id,requires_inventory_posting,gross_value,recoverable_value,"
            "net_loss_value,notes,occurred_at,submitted_at,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,'production','PRODUCTION_ORDER',?,0,?,?,?,?,?,?,?,?)",
            (case.id, case.operation_id, case.branch_id, case.warehouse_id,
             case.reported_by_user_id, classification_id, case.reason_id,
             case.origin.value, case.status.value, case.source_document_id,
             str(case.gross_value), "0", str(case.net_loss_value), case.notes,
             case.created_at.isoformat(), now, case.created_at.isoformat(), now))
        for line in case.lines:
            self._db.execute(
                "INSERT INTO loss_lines (id,loss_case_id,product_id,lot_id,quantity,weight,unit,"
                "unit_cost,gross_value,recoverable_value,net_loss_value,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (line.id, case.id, line.product_id, line.lot_id, str(line.quantity),
                 str(line.weight), line.unit, str(line.unit_cost), str(line.gross_value),
                 str(line.recoverable_value), str(line.net_loss_value), now))

    def recent_variances(self, *, branch_id, limit=100):
        return self._db.execute(
            "SELECT y.id,y.production_order_id,y.product_id,y.expected_output,y.actual_output,"
            "y.variance_quantity,y.variance_rate,y.severity,y.detected_at "
            "FROM yield_variances y LEFT JOIN loss_cases lc ON lc.id=y.loss_case_id "
            "WHERE lc.branch_id=? ORDER BY y.detected_at DESC LIMIT ?",
            (branch_id, limit)).fetchall()

    def open_alerts(self, *, branch_id, limit=100):
        return self._db.execute(
            "SELECT a.id,a.yield_variance_id,a.severity,a.expected_yield_pct,"
            "a.actual_yield_pct,a.lower_tolerance_pct,a.upper_tolerance_pct,a.message,"
            "a.created_at FROM loss_yield_alerts a "
            "JOIN loss_cases lc ON lc.id=a.loss_case_id "
            "WHERE lc.branch_id=? AND a.status='OPEN' "
            "ORDER BY CASE a.severity WHEN 'CRITICAL' THEN 0 "
            "WHEN 'OUT_OF_TOLERANCE' THEN 1 ELSE 2 END,a.created_at DESC LIMIT ?",
            (branch_id, limit)).fetchall()
