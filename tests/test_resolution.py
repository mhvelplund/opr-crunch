"""Baseline attack resolution with no special rules in play."""

from fractions import Fraction

from opr_crunch.model import Scenario, resolve


def shooting(**overrides) -> Scenario:
    """A plain ranged attack; override only what a test is about."""
    base = dict(models=10, attacks=1, quality=4, defense=3, def_models=5)
    base.update(overrides)
    return Scenario(**base)


class TestHits:
    def test_hits_are_dice_times_quality_chance(self):
        # 10 models x 1 attack = 10 dice, Quality 4+ hits on 3 of 6 faces.
        assert resolve(shooting()).hits == Fraction(5)

    def test_multiple_attacks_multiply_the_dice_pool(self):
        assert resolve(shooting(attacks=3)).hits == Fraction(15)

    def test_worse_quality_lands_fewer_hits(self):
        assert resolve(shooting(quality=5)).hits == Fraction(10) * Fraction(2, 6)

    def test_a_single_model_still_rolls_its_attacks(self):
        assert resolve(shooting(models=1, attacks=2)).hits == Fraction(1)


class TestWounds:
    def test_wounds_are_hits_that_defense_fails_to_block(self):
        # 5 hits, Defense 3+ blocks on 4 of 6 faces, so 1/3 get through.
        assert resolve(shooting()).wounds == Fraction(5) * Fraction(2, 6)

    def test_ap_worsens_the_defense_roll(self):
        # The requirements' worked example: AP(1) pushes Defense 3 to a 4+.
        assert resolve(shooting(ap=1)).wounds == Fraction(5, 2)

    def test_ap_cannot_remove_the_natural_six_block(self):
        # Defense 3 with AP(5) needs an 8+, but an unmodified 6 always blocks.
        assert resolve(shooting(ap=5)).wounds == Fraction(5) * Fraction(5, 6)

    def test_tougher_defense_blocks_more(self):
        assert resolve(shooting(defense=2)).wounds == Fraction(5) * Fraction(1, 6)


class TestCover:
    def test_cover_improves_the_defense_roll_when_shot_at(self):
        # Defense 3 with AP(1) is a 4+; cover pulls it back to a 3+.
        assert resolve(shooting(ap=1, in_cover=True)).wounds == Fraction(5) * Fraction(2, 6)

    def test_cover_does_not_apply_in_melee(self):
        melee = shooting(ap=1, in_cover=True, combat="Melee")
        assert resolve(melee).wounds == Fraction(5, 2)
