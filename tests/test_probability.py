"""Dice primitives from Core Rules v3.5.1 general principles.

"Quality Tests: Roll one six-sided die, and if you score the model's quality
value or higher, then it counts as a success."
"Modifiers: Regardless of modifiers, rolls of 6 always succeed, and rolls of 1
always fail."
"""

from fractions import Fraction

import pytest

from opr_crunch.model import p_block_no6, p_success


class TestPSuccess:
    @pytest.mark.parametrize(
        "target,expected",
        [
            (2, Fraction(5, 6)),  # 2,3,4,5,6 succeed
            (3, Fraction(4, 6)),
            (4, Fraction(3, 6)),
            (5, Fraction(2, 6)),
            (6, Fraction(1, 6)),
        ],
    )
    def test_unmodified_targets(self, target, expected):
        assert p_success(target) == expected

    def test_natural_1_always_fails_so_target_1_is_not_certain(self):
        """A target of 1+ cannot succeed on a roll of 1, capping success at 5/6."""
        assert p_success(1) == Fraction(5, 6)

    def test_natural_1_clamp_holds_for_targets_below_1(self):
        assert p_success(-3) == Fraction(5, 6)

    @pytest.mark.parametrize("target", [7, 8, 12])
    def test_natural_6_always_succeeds_so_impossible_targets_still_hit(self, target):
        """AP can drive the target past 6, but an unmodified 6 always blocks."""
        assert p_success(target) == Fraction(1, 6)


class TestPBlockNo6:
    """Bane removes the natural 6 auto-block, so it needs the 2..5 faces only."""

    @pytest.mark.parametrize(
        "target,expected",
        [
            (2, Fraction(4, 6)),  # 2,3,4,5
            (3, Fraction(3, 6)),  # 3,4,5
            (4, Fraction(2, 6)),  # 4,5
            (5, Fraction(1, 6)),  # 5
            (6, Fraction(0, 6)),  # only the 6 would have blocked
        ],
    )
    def test_excludes_the_natural_six(self, target, expected):
        assert p_block_no6(target) == expected

    def test_impossible_target_blocks_nothing_without_the_six(self):
        assert p_block_no6(9) == Fraction(0, 6)

    def test_natural_1_still_fails(self):
        assert p_block_no6(1) == Fraction(4, 6)
