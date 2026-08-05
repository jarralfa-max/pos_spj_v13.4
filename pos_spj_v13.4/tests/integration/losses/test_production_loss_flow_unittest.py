import importlib
import sqlite3
import unittest
from decimal import Decimal

from backend.application.losses.execution_context import LossExecutionContext
from backend.application.losses.production_loss import AnalyzeProductionLossCommand, ProductionLossAnalysisService, ProductionOutputInput
from backend.application.losses.yield_queries import YieldMonitoringQueryService
from backend.domain.products.entities.cutting_output import MeasureKind
from backend.domain.products.recipe_enums import OutputType
from backend.infrastructure.db.schema.products_schema import create_products_schema
from backend.infrastructure.persistence.production_loss_repository import ProductionLossRepository
from backend.shared.ids import new_uuid


class _Allow:
    def require(self, _actor, _permission): pass


class ProductionLossFlowTest(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        create_products_schema(self.db)
        importlib.import_module("migrations.standalone.174_losses_bounded_context_schema").run(self.db)
        self.actor, self.branch, self.warehouse = new_uuid(), new_uuid(), new_uuid()
        self.input_product, self.output_product, self.co_product, self.by_product, self.unit = (new_uuid() for _ in range(5))
        self.species, self.region, self.main_cut, self.by_cut = (new_uuid() for _ in range(4))
        self.db.execute("INSERT INTO species (id,code,name) VALUES (?, 'BOVINE','Bovino')", (self.species,))
        self.db.execute("INSERT INTO anatomical_regions (id,species_id,code,name) VALUES (?,?,'CARCASS','Canal')", (self.region,self.species))
        for cut_id, code, name in ((self.main_cut,"LOIN","Lomo"),(self.by_cut,"TRIM","Recorte")):
            self.db.execute("INSERT INTO cut_classifications (id,species_id,anatomical_region_id,code,name,cut_level) VALUES (?,?,?,?,?,'PRIMARY')",
                            (cut_id,self.species,self.region,code,name))
        for identifier, code, name in ((self.input_product,"INPUT","Canal"),(self.output_product,"OUTPUT","Corte"),(self.co_product,"CO","Hueso"),(self.by_product,"BY","Recorte")):
            self.db.execute(
                "INSERT INTO products (id,code,name,product_type,base_unit_id,lifecycle_status,species_id) "
                "VALUES (?,?,?,?,?,'ACTIVE',?)", (identifier, code, name, "MEAT", self.unit,self.species))
        self.recipe, self.recipe_version = new_uuid(), new_uuid()
        self.profile, self.profile_version = new_uuid(), new_uuid()
        self.db.execute("INSERT INTO recipes (id,product_id,recipe_type,name) VALUES (?,?,?,?)",
                        (self.recipe, self.input_product, "DISASSEMBLY", "Despiece"))
        self.db.execute("INSERT INTO recipe_versions (id,recipe_id,version_number,status) VALUES (?,?,1,'ACTIVE')",
                        (self.recipe_version, self.recipe))
        self.db.execute("INSERT INTO yield_profiles (id,input_product_id,name) VALUES (?,?,?)",
                        (self.profile, self.input_product, "Rendimiento estándar"))
        self.db.execute("INSERT INTO yield_profile_versions (id,yield_profile_id,version_number,status,tolerance_pct) VALUES (?,?,1,'ACTIVE','2')",
                        (self.profile_version, self.profile))
        self.db.execute(
            "INSERT INTO yield_outputs (id,version_id,product_id,output_type,expected_yield_pct,unit_id) "
            "VALUES (?,?,?,'MAIN_PRODUCT','70',?)",
            (new_uuid(), self.profile_version, self.output_product, self.unit))
        self.db.execute(
            "INSERT INTO yield_outputs (id,version_id,product_id,output_type,expected_yield_pct,unit_id) VALUES (?,?,?,'CO_PRODUCT','10',?)",
            (new_uuid(),self.profile_version,self.co_product,self.unit))
        self.db.execute(
            "INSERT INTO yield_outputs (id,version_id,product_id,output_type,expected_yield_pct,unit_id) VALUES (?,?,?,'BY_PRODUCT','10',?)",
            (new_uuid(),self.profile_version,self.by_product,self.unit))
        self.scheme, self.scheme_version = new_uuid(), new_uuid()
        self.db.execute("INSERT INTO cutting_schemes (id,input_product_id,species_id,name) VALUES (?,?,?,'Despiece bovino')",
                        (self.scheme,self.input_product,self.species))
        self.db.execute("INSERT INTO cutting_scheme_versions (id,cutting_scheme_id,version_number,status) VALUES (?,?,1,'ACTIVE')",
                        (self.scheme_version,self.scheme))
        self.db.execute("INSERT INTO cutting_outputs (id,version_id,product_id,output_type,measure_kind,quantity,unit_id,cut_classification_id) VALUES (?,?,?,'MAIN_PRODUCT','BY_PIECE','7',?,?)",
                        (new_uuid(),self.scheme_version,self.output_product,self.unit,self.main_cut))
        self.db.execute("INSERT INTO cutting_outputs (id,version_id,product_id,output_type,measure_kind,quantity,unit_id,cut_classification_id) VALUES (?,?,?,'CO_PRODUCT','BY_WEIGHT','10',?,?)",
                        (new_uuid(),self.scheme_version,self.co_product,self.unit,self.by_cut))
        self.db.execute("INSERT INTO cutting_outputs (id,version_id,product_id,output_type,measure_kind,quantity,unit_id,cut_classification_id) VALUES (?,?,?,'BY_PRODUCT','BY_WEIGHT','14',?,?)",
                        (new_uuid(),self.scheme_version,self.by_product,self.unit,self.by_cut))
        self.db.commit()
        self.context = LossExecutionContext(
            self.actor, self.branch, frozenset({self.branch}), frozenset({self.warehouse}))
        self.service = ProductionLossAnalysisService(
            ProductionLossRepository(self.db), _Allow())

    def tearDown(self): self.db.close()

    def test_abnormal_run_creates_normal_and_variance_cases_once(self):
        operation = new_uuid()
        command = AnalyzeProductionLossCommand(
            operation, new_uuid(), self.recipe_version, self.profile_version,
            self.input_product, Decimal("100"),
            (ProductionOutputInput(self.output_product, Decimal("60"), output_type=OutputType.MAIN_PRODUCT,
                                   quantity=Decimal("6"), species_id=self.species,
                                   cut_classification_id=self.main_cut, measure_kind=MeasureKind.BY_PIECE),
             ProductionOutputInput(self.co_product, Decimal("10"), output_type=OutputType.CO_PRODUCT,
                                   species_id=self.species, cut_classification_id=self.by_cut,
                                   measure_kind=MeasureKind.BY_WEIGHT),
             ProductionOutputInput(self.by_product, Decimal("14"), output_type=OutputType.BY_PRODUCT,
                                   species_id=self.species, cut_classification_id=self.by_cut,
                                   measure_kind=MeasureKind.BY_WEIGHT)),
            self.context, self.warehouse, self.scheme_version)
        first = self.service.execute(command)
        replay = self.service.execute(command)
        self.assertEqual(Decimal("10"), first.normal_loss_weight)
        self.assertEqual(Decimal("6"), first.abnormal_loss_weight)
        self.assertTrue(replay.replayed)
        self.assertEqual(2, self.db.execute("SELECT COUNT(*) FROM loss_cases").fetchone()[0])
        self.assertEqual(1, self.db.execute("SELECT COUNT(*) FROM yield_variances").fetchone()[0])
        alert = self.db.execute(
            "SELECT severity,expected_yield_pct,actual_yield_pct,lower_tolerance_pct,"
            "upper_tolerance_pct,status FROM loss_yield_alerts").fetchone()
        self.assertEqual(("OUT_OF_TOLERANCE","90","84.00","88","92","OPEN"), alert)
        self.assertEqual(first.alert_id, replay.alert_id)
        self.assertEqual(1, self.db.execute(
            "SELECT COUNT(*) FROM loss_outbox WHERE event_name='YIELD_ALERT_RAISED'").fetchone()[0])
        rows = self.db.execute(
            "SELECT c.code,l.weight,lc.requires_inventory_posting FROM loss_cases lc "
            "JOIN loss_classifications c ON c.id=lc.classification_id "
            "JOIN loss_lines l ON l.loss_case_id=lc.id ORDER BY c.code").fetchall()
        self.assertEqual([("PROCESS_LOSS", "10", 0), ("YIELD_VARIANCE", "6", 0)], rows)
        observations = self.db.execute(
            "SELECT output_type,measure_kind,quantity,weight FROM loss_meat_output_observations ORDER BY output_type").fetchall()
        self.assertEqual([("BY_PRODUCT","BY_WEIGHT","0","14"),
                          ("CO_PRODUCT","BY_WEIGHT","0","10"),
                          ("MAIN_PRODUCT","BY_PIECE","6","60")], observations)
        monitoring = YieldMonitoringQueryService(ProductionLossRepository(self.db))
        self.assertEqual(Decimal("-6.00"), monitoring.recent_variances(
            branch_id=self.branch)[0].variance_pct)
        self.assertEqual(first.alert_id, monitoring.open_alerts(
            branch_id=self.branch)[0].id)


if __name__ == "__main__": unittest.main()
