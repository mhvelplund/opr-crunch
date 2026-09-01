"""Points cost of a fielded unit, and the efficiency it buys.

A book prices a unit at its listed size — "Warriors [5] - 100pts" is five
models with their starting weapons. Fielding the doubled unit doubles the
bill, upgrades included.
"""

from fractions import Fraction

import pytest

from opr_crunch.model import cost_per_wound, unit_cost, valid_model_counts


class TestValidModelCounts:
    """A unit is fielded at its listed size, or at double it."""

    def test_a_multi_model_unit_may_be_doubled(self):
        assert valid_model_counts(5) == [5, 10]

    def test_doubling_follows_the_units_own_size(self):
        assert valid_model_counts(3) == [3, 6]

    def test_a_single_model_unit_cannot_be_doubled(self):
        assert valid_model_counts(1) == [1]

    @pytest.mark.parametrize("size", [0, -1])
    def test_an_unknown_size_offers_nothing(self, size):
        """A blank or unrecognised unit looks up as size 0, not as a 1-model unit."""
        assert valid_model_counts(size) == []


class TestUnitCost:
    """Cost of the models actually fielded, from the book's price for its size."""

    def test_the_listed_size_costs_the_listed_price(self):
        assert unit_cost(base=100, weapon=0, upgrade=0, size=5, models=5) == 100

    def test_doubling_the_models_doubles_the_price(self):
        assert unit_cost(base=100, weapon=0, upgrade=0, size=5, models=10) == 200

    def test_a_weapon_swap_is_added_before_doubling(self):
        """5 Warriors with Gauss Rifles cost 110; 10 of them cost 220."""
        assert unit_cost(base=100, weapon=10, upgrade=0, size=5, models=5) == 110
        assert unit_cost(base=100, weapon=10, upgrade=0, size=5, models=10) == 220

    def test_an_upgrade_is_added_before_doubling(self):
        assert unit_cost(base=100, weapon=0, upgrade=15, size=5, models=10) == 230

    def test_a_single_model_unit_costs_its_price(self):
        assert unit_cost(base=175, weapon=0, upgrade=0, size=1, models=1) == 175

    def test_an_unknown_size_costs_nothing(self):
        """Guards the division: a blank row must not raise."""
        assert unit_cost(base=100, weapon=10, upgrade=0, size=0, models=5) == 0

    def test_an_illegal_count_scales_proportionally(self):
        """The sheet flags such a count red rather than refusing to price it."""
        assert unit_cost(base=100, weapon=0, upgrade=0, size=5, models=7) == Fraction(140)


class TestCostPerWound:
    """Points spent per projected wound — lower is more efficient."""

    def test_divides_cost_by_projected_wounds(self):
        assert cost_per_wound(Fraction(100), Fraction(4)) == 25

    def test_keeps_the_fraction_exact(self):
        assert cost_per_wound(Fraction(100), Fraction(3)) == Fraction(100, 3)

    def test_no_projected_wounds_has_no_cost_per_wound(self):
        """None is what the sheet renders as an infinity marker."""
        assert cost_per_wound(Fraction(100), Fraction(0)) is None
