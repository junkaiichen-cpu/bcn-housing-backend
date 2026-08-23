import unittest

from valuation_helpers import (
    build_valuation_benchmark,
    compare_user_price,
    normalize_contract_type,
    normalize_rental_type,
)


class ValuationHelperTests(unittest.TestCase):
    def test_empty_user_price_still_returns_prediction_context(self):
        result = compare_user_price(None, 1350.0, 1280.0, 1420.0)
        self.assertFalse(result["provided"])
        self.assertEqual(result["assessment"], "not_provided")
        self.assertEqual(result["estimated_range"]["max"], 1420.0)

    def test_monthly_user_price_is_compared_to_prediction(self):
        result = compare_user_price(1450.0, 1350.0, 1280.0, 1420.0)
        self.assertTrue(result["provided"])
        self.assertEqual(result["period"], "monthly")
        self.assertEqual(result["assessment"], "above_expected")
        self.assertAlmostEqual(result["difference_percent"], 7.41, places=2)

    def test_rental_type_labels_support_more_than_entire_and_room(self):
        self.assertEqual(normalize_rental_type("studio")["label_zh"], "Studio")
        self.assertEqual(normalize_rental_type("private_room")["label_zh"], "独立卧室")
        self.assertEqual(normalize_rental_type("shared_room")["label_zh"], "共享卧室")

    def test_contract_labels_accept_user_facing_translation(self):
        self.assertEqual(normalize_contract_type("长期住宅合同"), "LAU_LONG_TERM")
        self.assertEqual(normalize_contract_type("季节性 / 临时租赁合同"), "TEMPORADA")
        self.assertEqual(normalize_contract_type("合租房间合同"), "ROOM")

    def test_benchmark_contains_core_metrics(self):
        benchmark = build_valuation_benchmark(
            estimated_monthly_rent=1350.0,
            estimated_min=1280.0,
            estimated_max=1420.0,
            area_sqm=60.0,
            avg_rent_sqm=22.5,
            loc={"comarca": "Barcelonès", "municipio": "Barcelona", "barrio": "Eixample"},
            rental_type="entire",
            floor_level="Middle",
            has_elevator=True,
            condition="good",
            contract_type="LAU_LONG_TERM",
        )
        self.assertIn("estimated_rent", benchmark)
        self.assertIn("price_per_sqm", benchmark)
        self.assertEqual(benchmark["area"]["value"], "60 m²")
        self.assertEqual(benchmark["contract_type"]["value"], "长期住宅合同")


if __name__ == "__main__":
    unittest.main()
