"""Rules introduced by the Robot Legions army book (GF - Robot Legions v3.5.3).

Baseline throughout: 10 models, 1 attack, Quality 4, vs Defense 3, 5 defenders.
That is 10 dice, 5 hits, of which 10/6 are unmodified 6s, and 10/6 wounds.
"""

from fractions import Fraction

import pytest

from opr_crunch.model import Scenario, resolve

BASE_WOUNDS = Fraction(10, 6)
H6 = Fraction(10, 6)


def shooting(**overrides) -> Scenario:
    base = dict(models=10, attacks=1, quality=4, defense=3, def_models=5)
    base.update(overrides)
    return Scenario(**base)


def melee(**overrides) -> Scenario:
    return shooting(combat="Melee", **overrides)


class TestShred:
    """Shred: on unmodified results of 1 to block hits, deals 1 extra wound."""

    def test_adds_a_wound_per_defence_roll_of_one(self):
        got = resolve(shooting(att_rules={"Shred"}))
        assert got.wounds == BASE_WOUNDS + Fraction(5) * Fraction(1, 6)

    def test_the_original_worked_example(self):
        """10 Warriors, AP(1) Reaper rifles with Shred, vs 5 Battle Brothers.

        This is the 3.33 from the first draft of the requirements.
        """
        got = resolve(shooting(ap=1, att_rules={"Shred"}))
        assert got.wounds == Fraction(10, 3)

    def test_the_extra_wound_is_independent_of_ap(self):
        """A roll of 1 is unmodified, so AP does not change how often it happens."""
        plain = resolve(shooting(ap=2))
        shred = resolve(shooting(ap=2, att_rules={"Shred"}))
        assert shred.wounds - plain.wounds == Fraction(5) * Fraction(1, 6)

    def test_does_not_change_hits(self):
        assert resolve(shooting(att_rules={"Shred"})).hits == Fraction(5)


class TestDestructive:
    """Destructive: on unmodified results of 6 to hit, those hits get AP(+4)."""

    def test_natural_sixes_get_ap_four(self):
        expected = H6 * Fraction(5, 6) + Fraction(20, 6) * Fraction(2, 6)
        assert resolve(shooting(att_rules={"Destructive"})).wounds == expected

    def test_unlike_rending_it_does_not_bypass_regeneration(self):
        got = resolve(shooting(att_rules={"Destructive"}, def_rules={"Regeneration"}))
        without = resolve(shooting(att_rules={"Destructive"}))
        assert got.wounds == without.wounds * Fraction(2, 3)


class TestSelfRepair:
    """Self-Repair: roll a die per wound; on a 6+ it is ignored."""

    def test_ignores_a_sixth_of_wounds(self):
        got = resolve(shooting(def_rules={"Self-Repair"}))
        assert got.wounds == BASE_WOUNDS * Fraction(5, 6)

    @pytest.mark.parametrize("rule", ["Bane", "Rending", "Unstoppable"])
    def test_is_not_cancelled_by_rules_that_ignore_regeneration(self, rule):
        with_sr = resolve(shooting(def_rules={"Self-Repair"}, att_rules={rule}))
        without = resolve(shooting(att_rules={rule}))
        assert with_sr.wounds == without.wounds * Fraction(5, 6)


class TestSelfRepairBoost:
    """Self-Repair Boost: ignore wounds on 5-6 instead of only 6+."""

    def test_ignores_a_third_of_wounds(self):
        got = resolve(shooting(def_rules={"Self-Repair", "Self-Repair Boost"}))
        assert got.wounds == BASE_WOUNDS * Fraction(4, 6)

    def test_supersedes_plain_self_repair(self):
        boosted = resolve(shooting(def_rules={"Self-Repair", "Self-Repair Boost"}))
        alone = resolve(shooting(def_rules={"Self-Repair Boost"}))
        assert boosted.wounds == alone.wounds


class TestProtected:
    """Protected: roll a die per wound; on a 6+ it is ignored."""

    def test_ignores_a_sixth_of_wounds(self):
        assert resolve(shooting(def_rules={"Protected"})).wounds == BASE_WOUNDS * Fraction(5, 6)

    def test_the_best_ignore_roll_applies_once_not_twice(self):
        """Stacked ignore rules take the best threshold rather than compounding."""
        both = resolve(shooting(def_rules={"Protected", "Regeneration"}))
        assert both.wounds == BASE_WOUNDS * Fraction(4, 6)


class TestShielded:
    """Shielded: +1 to Defense rolls against hits that are not from spells."""

    def test_improves_the_defence_roll(self):
        # Defense 3 becomes a 2+, blocked on 5 of 6 faces.
        got = resolve(shooting(def_rules={"Shielded"}))
        assert got.wounds == Fraction(5) * Fraction(1, 6)

    def test_stacks_with_cover(self):
        # Defense 3, +2 from AP, -1 cover, -1 Shielded: still a 3+ to block.
        got = resolve(shooting(ap=2, def_rules={"Shielded"}, in_cover=True))
        assert got.wounds == Fraction(5) * (1 - Fraction(4, 6))


class TestRavage:
    """Ravage(X): in melee roll X dice; for each 6+ the target takes one wound."""

    def test_adds_direct_wounds_in_melee(self):
        got = resolve(melee(ravage=2))
        assert got.wounds == BASE_WOUNDS + Fraction(10 * 2, 6)

    def test_does_nothing_at_range(self):
        assert resolve(shooting(ravage=2)).wounds == BASE_WOUNDS

    def test_wounds_bypass_the_defence_roll(self):
        """Ravage inflicts wounds directly, so Defense does not reduce them."""
        tough_target = resolve(melee(ravage=2, defense=2))
        expected = Fraction(5) * (1 - Fraction(5, 6)) + Fraction(20, 6)
        assert tough_target.wounds == expected

    def test_does_not_count_as_hits(self):
        assert resolve(melee(ravage=2)).hits == Fraction(5)

    def test_is_still_subject_to_self_repair(self):
        got = resolve(melee(ravage=2, def_rules={"Self-Repair"}))
        assert got.wounds == (BASE_WOUNDS + Fraction(20, 6)) * Fraction(5, 6)


class TestPiercingAssault:
    """Piercing Assault: this model gets AP(+1) when charging."""

    def test_adds_ap_on_a_charge(self):
        got = resolve(melee(melee_state="Charging", att_rules={"Piercing Assault"}))
        assert got.wounds == Fraction(5) * Fraction(3, 6)

    def test_does_nothing_without_a_charge(self):
        assert resolve(melee(att_rules={"Piercing Assault"})).wounds == BASE_WOUNDS


class TestRuleNamesThatContainOtherRules:
    """The sheet detects rules by substring, so the model must agree.

    Army books grant rules through wrappers - "Relentless Aura", "Self-Repair
    Boost Buff", "Unstoppable when Shooting" - and a unit that has the wrapper
    has the rule.
    """

    def test_an_aura_grants_the_rule_it_names(self):
        aura = resolve(shooting(att_rules={"Relentless Aura"}))
        plain = resolve(shooting(att_rules={"Relentless"}))
        assert aura.hits == plain.hits

    def test_self_repair_boost_buff_counts_as_the_boost(self):
        buffed = resolve(shooting(def_rules={"Self-Repair Boost Buff"}))
        assert buffed.wounds == BASE_WOUNDS * Fraction(4, 6)

    def test_unstoppable_when_shooting_counts_as_unstoppable(self):
        got = resolve(shooting(def_rules={"Regeneration"},
                               att_rules={"Unstoppable when Shooting"}))
        assert got.wounds == BASE_WOUNDS


class TestTough:
    """Tough(X): the model takes X wounds before dying, so Deadly cannot overflow."""

    def test_deadly_is_capped_by_the_targets_tough_value(self):
        got = resolve(shooting(deadly=3, tough=2))
        assert got.wounds == BASE_WOUNDS * 2

    def test_deadly_pays_off_in_full_against_a_tougher_target(self):
        assert resolve(shooting(deadly=3, tough=6)).wounds == BASE_WOUNDS * 3

    def test_deadly_is_wasted_on_models_without_tough(self):
        """Deadly's wounds don't carry over, so a 1-wound model absorbs only one."""
        assert resolve(shooting(deadly=3)).wounds == BASE_WOUNDS

    def test_tough_alone_does_not_change_wounds(self):
        assert resolve(shooting(tough=6)).wounds == BASE_WOUNDS


# ---------------------------------------------------------------------------
# Havoc Brothers army book
# ---------------------------------------------------------------------------

# Branch A is AP(+1): Defense 3 becomes a 4+, so half the hits wound.
BRANCH_AP_HITS, BRANCH_AP_WOUNDS = Fraction(5), Fraction(5, 2)
# Branch B is +1 to hit: Quality 4 becomes a 3+, and Defense stays a 3+.
BRANCH_HIT_HITS, BRANCH_HIT_WOUNDS = Fraction(20, 3), Fraction(20, 9)


class TestHavocbound:
    """AP(+1) when shooting at enemies over 9" away, or when charging."""

    def test_applies_when_shooting_beyond_nine_inches(self):
        got = resolve(shooting(att_rules={"Havocbound"}, long_range=True))
        assert got.wounds == BRANCH_AP_WOUNDS

    def test_does_not_apply_inside_nine_inches(self):
        got = resolve(shooting(att_rules={"Havocbound"}, long_range=False))
        assert got.wounds == BASE_WOUNDS

    def test_applies_when_charging(self):
        got = resolve(melee(melee_state="Charging", att_rules={"Havocbound"}))
        assert got.wounds == BRANCH_AP_WOUNDS

    def test_does_not_apply_in_melee_without_a_charge(self):
        assert resolve(melee(att_rules={"Havocbound"})).wounds == BASE_WOUNDS

    def test_an_aura_that_names_it_grants_it(self):
        got = resolve(shooting(att_rules={"Havocbound Boost Aura"}, long_range=True))
        assert got.wounds == BRANCH_AP_WOUNDS


class TestUnpredictable:
    """A die decides: on 1-3 AP(+1), on 4-6 +1 to hit. So a 50/50 average."""

    def test_hits_are_the_average_of_both_branches(self):
        got = resolve(shooting(att_rules={"Unpredictable"}))
        assert got.hits == (BRANCH_AP_HITS + BRANCH_HIT_HITS) / 2

    def test_wounds_are_the_average_of_both_branches(self):
        got = resolve(shooting(att_rules={"Unpredictable"}))
        assert got.wounds == (BRANCH_AP_WOUNDS + BRANCH_HIT_WOUNDS) / 2

    def test_it_applies_in_melee_too(self):
        got = resolve(melee(att_rules={"Unpredictable"}))
        assert got.hits == (BRANCH_AP_HITS + BRANCH_HIT_HITS) / 2


class TestUnpredictableFighter:
    """The same die, but only in melee - and its name contains Unpredictable."""

    def test_applies_in_melee(self):
        got = resolve(melee(att_rules={"Unpredictable Fighter"}))
        assert got.wounds == (BRANCH_AP_WOUNDS + BRANCH_HIT_WOUNDS) / 2

    def test_does_nothing_at_range(self):
        """Substring matching must not let it stand in for plain Unpredictable."""
        got = resolve(shooting(att_rules={"Unpredictable Fighter"}))
        assert got.wounds == BASE_WOUNDS
        assert got.hits == Fraction(5)


class TestVersatileAttack:
    """The player picks the effect, so the sheet takes the pick rather than averaging."""

    def test_choosing_ap(self):
        got = resolve(shooting(att_rules={"Versatile Attack"}, variable_choice="AP"))
        assert (got.hits, got.wounds) == (BRANCH_AP_HITS, BRANCH_AP_WOUNDS)

    def test_choosing_to_hit(self):
        got = resolve(shooting(att_rules={"Versatile Attack"}, variable_choice="To-hit"))
        assert (got.hits, got.wounds) == (BRANCH_HIT_HITS, BRANCH_HIT_WOUNDS)

    def test_only_applies_beyond_nine_inches(self):
        got = resolve(shooting(att_rules={"Versatile Attack"}, long_range=False))
        assert got.wounds == BASE_WOUNDS

    def test_a_defensive_aura_of_a_similar_name_does_not_trigger_it(self):
        got = resolve(shooting(att_rules={"Versatile Defense Aura"}))
        assert got.wounds == BASE_WOUNDS


class TestNoVariableRule:
    def test_the_choice_column_is_inert_without_one_of_these_rules(self):
        for choice in ("AP", "To-hit"):
            assert resolve(shooting(variable_choice=choice)).wounds == BASE_WOUNDS
