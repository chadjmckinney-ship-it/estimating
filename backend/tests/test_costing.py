"""Pure-function tests for per-pour cost allocation and markup. No live DB."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.costing import (
    allocate_amount,
    is_cy_driven,
    per_sf,
    roll_coverage_sf,
    sale_from_cost,
    sf_per_cy,
)


class SfPerCyTests(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(sf_per_cy(Decimal("2942"), Decimal("108.3522")), Decimal("27.1522"))

    def test_zero_cy_is_blank(self):
        self.assertIsNone(sf_per_cy(Decimal("1000"), Decimal("0")))
        self.assertIsNone(sf_per_cy(Decimal("1000"), None))


class MarkupTests(unittest.TestCase):
    def test_default_margin_and_contingency(self):
        # 20% + 3% = × 1.23
        self.assertEqual(
            sale_from_cost(Decimal("10000.00"), Decimal("0.20"), Decimal("0.03")),
            Decimal("12300.00"),
        )

    def test_zero_markup(self):
        self.assertEqual(
            sale_from_cost(Decimal("50.00"), Decimal("0"), Decimal("0")),
            Decimal("50.00"),
        )


class AllocateTests(unittest.TestCase):
    def test_sf_share_ties(self):
        parts = allocate_amount(Decimal("1000.00"), [Decimal("100"), Decimal("200"), Decimal("700")])
        self.assertEqual(parts, [Decimal("100.00"), Decimal("200.00"), Decimal("700.00")])
        self.assertEqual(sum(parts), Decimal("1000.00"))

    def test_remainder_cents_go_to_last_pour(self):
        parts = allocate_amount(Decimal("10.00"), [Decimal("1"), Decimal("1"), Decimal("1")])
        self.assertEqual(parts[0], Decimal("3.33"))
        self.assertEqual(parts[1], Decimal("3.33"))
        self.assertEqual(parts[2], Decimal("3.34"))
        self.assertEqual(sum(parts), Decimal("10.00"))

    def test_zero_weights_dump_on_last(self):
        parts = allocate_amount(Decimal("5.00"), [Decimal("0"), Decimal("0")])
        self.assertEqual(parts, [Decimal("0.00"), Decimal("5.00")])

    def test_off_line_is_zero(self):
        parts = allocate_amount(Decimal("0.00"), [Decimal("10"), Decimal("90")])
        self.assertEqual(parts, [Decimal("0.00"), Decimal("0.00")])


class DriverTests(unittest.TestCase):
    def test_pumping_is_cy(self):
        self.assertTrue(is_cy_driven("CY"))
        self.assertTrue(is_cy_driven("/CY"))
        self.assertFalse(is_cy_driven("/SF"))
        self.assertFalse(is_cy_driven("DAY"))
        self.assertFalse(is_cy_driven("/FF"))
        self.assertFalse(is_cy_driven("LS"))


class CatalogHelpers(unittest.TestCase):
    def test_roll_coverage(self):
        self.assertEqual(roll_coverage_sf("10 mil 20 x 100"), Decimal("2000"))
        self.assertEqual(roll_coverage_sf("10 mil. Stego Wrap 14 x 210"), Decimal("2940"))
        self.assertEqual(roll_coverage_sf("15 mil Stego Wrap 14' x 140'"), Decimal("1960"))
        self.assertIsNone(roll_coverage_sf("Stego Tape"))

    def test_per_sf_blank_on_zero(self):
        self.assertIsNone(per_sf(Decimal("100"), Decimal("0")))
        self.assertEqual(per_sf(Decimal("100.00"), Decimal("50")), Decimal("2.0000"))


if __name__ == "__main__":
    unittest.main()