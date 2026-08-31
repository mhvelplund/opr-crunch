"""Each special rule from Core Rules v3.5.1 that affects hit/wound projection.

Baseline throughout: 10 models, 1 attack, Quality 4, vs Defense 3, 5 defenders.
That is 10 dice, 5 hits, of which 10/6 are unmodified 6s.
"""

from fractions import Fraction

import pytest

from opr_crunch.model import Scenario, resolve

H6 = Fraction(10, 6)  # natural-6 hits in the baseline pool


def shooting(**overrides) -> Scenario:
    base = dict(models=10, attacks=1, quality=4, defense=3, def_models=5)
    base.update(overrides)
    return Scenario(**base)


def melee(**overrides) -> Scenario:
    return shooting(combat="Melee", **overrides)


def charge(**overrides) -> Scenario:
    return melee(melee_state="Charging", **overrides)


class TestReliable:
    """Reliable: Attacks at Quality 2+."""

    def test_attacks_at_quality_two(self):
        assert resolve(shooting(att_rules={"Reliable"})).hits == 10 * Fraction(5, 6)

    def test_does_not_worsen_an_already_better_quality(self):
        assert resolve(shooting(quality=2, att_rules={"Reliable"})).hits == 10 * Fraction(5, 6)


class TestExtraHitsOnSixes:
    """Surge, Relentless and Furious each add 1 hit per unmodified 6 to hit."""

    def test_surge_adds_a_hit_per_natural_six(self):
        assert resolve(shooting(att_rules={"Surge"})).hits == Fraction(5) + H6

    def test_relentless_applies_when_shooting_over_nine_inches(self):
        got = resolve(shooting(att_rules={"Relentless"}, long_range=True))
        assert got.hits == Fraction(5) + H6

    def test_relentless_does_nothing_inside_nine_inches(self):
        assert resolve(shooting(att_rules={"Relentless"}, long_range=False)).hits == Fraction(5)

    def test_relentless_does_nothing_in_melee(self):
        assert resolve(melee(att_rules={"Relentless"})).hits == Fraction(5)

    def test_furious_applies_when_charging_in_melee(self):
        assert resolve(charge(att_rules={"Furious"})).hits == Fraction(5) + H6

    def test_furious_does_nothing_without_a_charge(self):
        assert resolve(melee(att_rules={"Furious"})).hits == Fraction(5)

    def test_furious_does_nothing_at_range(self):
        assert resolve(shooting(att_rules={"Furious"})).hits == Fraction(5)

    def test_extra_hit_rules_stack(self):
        got = resolve(shooting(att_rules={"Surge", "Relentless"}))
        assert got.hits == Fraction(5) + 2 * H6

    def test_extra_hits_are_not_themselves_natural_sixes(self):
        """Only the original hit counts as a 6, so Surge does not feed Rending."""
        surge = resolve(shooting(att_rules={"Surge", "Rending"}))
        rending_only = resolve(shooting(att_rules={"Rending"}))
        extra_wounds = H6 * (1 - Fraction(4, 6))  # extra hits resolve at base AP
        assert surge.wounds == rending_only.wounds + extra_wounds


class TestRending:
    """Rending: on unmodified 6s to hit, those hits get AP(+4)."""

    def test_natural_sixes_block_at_ap_four(self):
        # 10/6 hits vs Defense 3+AP4 = 7+, blocked only by a natural 6.
        # 20/6 hits vs Defense 3+, blocked on 4 of 6 faces.
        expected = H6 * Fraction(5, 6) + Fraction(20, 6) * Fraction(2, 6)
        assert resolve(shooting(att_rules={"Rending"})).wounds == expected

    def test_does_not_change_the_hit_count(self):
        assert resolve(shooting(att_rules={"Rending"})).hits == Fraction(5)


class TestAp:
    def test_ap_stacks_with_rending_on_the_six_pool(self):
        # Defense 3 + AP1 + 4 = 8+, still blocked by the natural 6 alone.
        expected = H6 * Fraction(5, 6) + Fraction(20, 6) * Fraction(3, 6)
        assert resolve(shooting(ap=1, att_rules={"Rending"})).wounds == expected


class TestBane:
    """Bane: the target must re-roll unmodified Defense results of 6."""

    def test_natural_six_is_rerolled_rather_than_blocking(self):
        # Blocks on 3,4,5 outright (3/6), plus the 6 re-rolled into a 4/6 block.
        block = Fraction(3, 6) + Fraction(1, 6) * Fraction(4, 6)
        assert resolve(shooting(att_rules={"Bane"})).wounds == Fraction(5) * (1 - block)


class TestBlast:
    """Blast(X): ignores cover, and each hit is multiplied by X, capped at models."""

    def test_multiplies_hits(self):
        assert resolve(shooting(blast=3)).hits == Fraction(15)

    def test_is_capped_at_the_target_model_count(self):
        assert resolve(shooting(blast=7, def_models=5)).hits == Fraction(25)

    def test_ignores_cover(self):
        with_cover = resolve(shooting(blast=2, ap=1, in_cover=True))
        without = resolve(shooting(blast=2, ap=1, in_cover=False))
        assert with_cover.wounds == without.wounds


class TestDeadly:
    """Deadly(X): each wound is multiplied by X, up to the target's Tough value."""

    def test_multiplies_wounds(self):
        assert resolve(shooting(deadly=2, tough=6)).wounds == 2 * resolve(shooting()).wounds

    def test_does_not_change_hits(self):
        assert resolve(shooting(deadly=3, tough=6)).hits == Fraction(5)


class TestRegeneration:
    """Regeneration: roll for each wound, on a 5+ it is ignored."""

    def test_ignores_a_third_of_wounds(self):
        got = resolve(shooting(def_rules={"Regeneration"}))
        assert got.wounds == resolve(shooting()).wounds * Fraction(2, 3)

    @pytest.mark.parametrize("rule", ["Bane", "Rending", "Unstoppable"])
    def test_is_bypassed_by_rules_that_ignore_it(self, rule):
        with_regen = resolve(shooting(def_rules={"Regeneration"}, att_rules={rule}))
        without = resolve(shooting(att_rules={rule}))
        assert with_regen.wounds == without.wounds


class TestThrust:
    """Thrust: when charging, gets +1 to hit rolls and AP(+1) in melee."""

    def test_improves_hit_rolls_when_charging(self):
        assert resolve(charge(att_rules={"Thrust"})).hits == 10 * Fraction(4, 6)

    def test_adds_ap_when_charging(self):
        # Quality 4 with +1 hits on 3+, Defense 3 with AP1 blocks on 4+.
        assert resolve(charge(att_rules={"Thrust"})).wounds == 10 * Fraction(4, 6) * Fraction(3, 6)

    def test_does_nothing_at_range(self):
        assert resolve(shooting(att_rules={"Thrust"})).hits == Fraction(5)

    def test_does_nothing_without_a_charge(self):
        assert resolve(melee(att_rules={"Thrust"})).hits == Fraction(5)


class TestImpact:
    """Impact(X): roll X dice when attacking after charging; each 2+ is a hit."""

    def test_adds_hits_when_charging(self):
        assert resolve(charge(impact=2)).hits == Fraction(5) + 20 * Fraction(5, 6)

    def test_does_nothing_without_a_charge(self):
        assert resolve(melee(impact=2)).hits == Fraction(5)

    def test_does_nothing_when_fatigued(self):
        fatigued = melee(impact=2, melee_state="Fatigued")
        assert resolve(fatigued).hits == resolve(melee(melee_state="Fatigued")).hits

    def test_impact_hits_carry_no_ap(self):
        # Impact hits resolve against an unmodified Defense 3+.
        impact_wounds = 20 * Fraction(5, 6) * Fraction(2, 6)
        assert resolve(charge(impact=2, ap=3)).wounds == (
            resolve(charge(ap=3)).wounds + impact_wounds
        )


class TestCounter:
    """Counter: the charging unit gets -1 total Impact rolls per model with Counter."""

    def test_defender_models_reduce_impact_dice(self):
        got = resolve(charge(impact=2, def_rules={"Counter"}))
        assert got.hits == Fraction(5) + (20 - 5) * Fraction(5, 6)

    def test_impact_dice_never_go_negative(self):
        got = resolve(charge(impact=1, def_models=50, def_rules={"Counter"}))
        assert got.hits == Fraction(5)


class TestFatigue:
    """After charging or striking back, units only hit on unmodified 6s in melee."""

    def test_fatigued_units_hit_only_on_sixes(self):
        assert resolve(melee(melee_state="Fatigued")).hits == 10 * Fraction(1, 6)

    def test_unstoppable_ignores_fatigue(self):
        got = resolve(melee(melee_state="Fatigued", att_rules={"Unstoppable"}))
        assert got.hits == Fraction(5)
