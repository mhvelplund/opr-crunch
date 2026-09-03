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


class TestLacerate:
    """Lacerate: the target must re-roll unmodified Defense results of 6.

    Same maths as Bane, but Lacerate does not bypass Regeneration.
    """

    def test_natural_six_is_rerolled_rather_than_blocking(self):
        block = Fraction(3, 6) + Fraction(1, 6) * Fraction(4, 6)
        assert resolve(shooting(att_rules={"Lacerate"})).wounds == Fraction(5) * (1 - block)

    def test_does_not_bypass_regeneration(self):
        with_regen = resolve(shooting(def_rules={"Regeneration"}, att_rules={"Lacerate"}))
        without = resolve(shooting(att_rules={"Lacerate"}))
        assert with_regen.wounds == without.wounds * Fraction(2, 3)


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


# ---------------------------------------------------------------------------
# Blessed Sisters army book
# ---------------------------------------------------------------------------


class TestDevout:
    """Devout: unmodified 6s to hit deal 1 extra hit. Unlike Relentless, this
    applies to every attack, ranged or melee, at any range."""

    def test_adds_a_hit_per_natural_six(self):
        got = resolve(shooting(att_rules={"Devout"}))
        assert got.hits == Fraction(5) + H6
        assert got.wounds == (Fraction(5) + H6) * Fraction(1, 3)

    def test_applies_in_melee_without_a_charge(self):
        got = resolve(melee(att_rules={"Devout"}))
        assert got.hits == Fraction(5) + H6


class TestDevoutBoost:
    """If this model has Devout, when it shoots or charges enemies over 9"
    away, naturals 5-6 (instead of only 6) each deal an extra hit."""

    def test_widens_the_bonus_to_naturals_five_and_six_past_nine_inches(self):
        got = resolve(shooting(att_rules={"Devout Boost"}, long_range=True))
        assert got.hits == Fraction(5) + 2 * H6
        assert got.wounds == (Fraction(5) + 2 * H6) * Fraction(1, 3)

    def test_is_inert_inside_nine_inches(self):
        """Only plain Devout's unconditional bonus applies (via substring match)."""
        got = resolve(shooting(att_rules={"Devout Boost"}, long_range=False))
        assert got.hits == Fraction(5) + H6

    def test_does_not_apply_in_melee_without_a_charge(self):
        got = resolve(melee(att_rules={"Devout Boost"}, long_range=True))
        assert got.hits == Fraction(5) + H6

    def test_applies_on_a_charge_from_over_nine_inches(self):
        got = resolve(
            melee(melee_state="Charging", att_rules={"Devout Boost"}, long_range=True)
        )
        assert got.hits == Fraction(5) + 2 * H6


class TestDisintegrate:
    """Ignores Regeneration, and gets AP(+2) against Defense 2-3 targets."""

    def test_bypasses_regeneration(self):
        with_regen = resolve(shooting(att_rules={"Disintegrate"}, def_rules={"Regeneration"}))
        without = resolve(shooting(att_rules={"Disintegrate"}))
        assert with_regen.wounds == without.wounds

    def test_adds_ap_two_against_defense_three(self):
        # AP(+2) makes Defense 3 into a 5+, blocked on 2 of 6 faces.
        got = resolve(shooting(att_rules={"Disintegrate"}))
        assert got.wounds == Fraction(5) * Fraction(2, 3)

    def test_adds_nothing_against_defense_four(self):
        got = resolve(shooting(att_rules={"Disintegrate"}, defense=4))
        plain = resolve(shooting(defense=4))
        assert got.wounds == plain.wounds


class TestFortified:
    """When a Fortified unit takes hits, those hits count as AP(-1), min AP(0)."""

    def test_reduces_incoming_ap_by_one(self):
        got = resolve(shooting(ap=2, def_rules={"Fortified"}))
        assert got.wounds == Fraction(5, 2)

    def test_never_pushes_ap_below_zero(self):
        assert resolve(shooting(def_rules={"Fortified"})).wounds == BASE_WOUNDS


class TestPointBlankSurgeDoesNotGrantPlainSurge:
    """"Point-Blank Surge" contains "Surge" but is a distinct, unmodelled,
    range-gated rule - it must not silently grant the unconditional bonus."""

    def test_is_inert(self):
        got = resolve(shooting(att_rules={"Point-Blank Surge"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


# ---------------------------------------------------------------------------
# Dao Union army book
# ---------------------------------------------------------------------------


class TestGoodShot:
    """Good Shot: +1 to hit rolls when shooting (not in melee)."""

    def test_adds_one_to_hit_when_shooting(self):
        got = resolve(shooting(att_rules={"Good Shot"}))
        assert got.hits == Fraction(20, 3)
        assert got.wounds == Fraction(20, 9)

    def test_does_not_apply_in_melee(self):
        got = resolve(melee(att_rules={"Good Shot"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestTargetingVisor:
    """Targeting Visor: +1 to hit rolls when shooting at enemies over 9" away."""

    def test_adds_one_to_hit_past_nine_inches(self):
        got = resolve(shooting(att_rules={"Targeting Visor"}, long_range=True))
        assert got.hits == Fraction(20, 3)
        assert got.wounds == Fraction(20, 9)

    def test_is_inert_inside_nine_inches(self):
        got = resolve(shooting(att_rules={"Targeting Visor"}, long_range=False))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_does_not_apply_in_melee(self):
        got = resolve(melee(att_rules={"Targeting Visor"}, long_range=True))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestStealth:
    """Stealth: enemies shooting this unit from over 9" away get -1 to hit."""

    def test_subtracts_one_to_hit_past_nine_inches(self):
        got = resolve(shooting(def_rules={"Stealth"}, long_range=True))
        assert got.hits == Fraction(10, 3)
        assert got.wounds == Fraction(10, 9)

    def test_is_inert_inside_nine_inches(self):
        got = resolve(shooting(def_rules={"Stealth"}, long_range=False))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_does_not_apply_in_melee(self):
        got = resolve(melee(def_rules={"Stealth"}, long_range=True))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestAircraft:
    """Aircraft: unconditional -1 to hit for anyone shooting at it."""

    def test_subtracts_one_to_hit_when_shot_at(self):
        got = resolve(shooting(def_rules={"Aircraft"}))
        assert got.hits == Fraction(10, 3)
        assert got.wounds == Fraction(10, 9)

    def test_is_inert_in_melee(self):
        got = resolve(melee(def_rules={"Aircraft"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestMeleeEvasion:
    """Melee Evasion: -1 to hit rolls in melee only, Stealth's melee counterpart."""

    def test_subtracts_one_to_hit_in_melee(self):
        got = resolve(melee(def_rules={"Melee Evasion"}))
        assert got.hits == Fraction(10, 3)
        assert got.wounds == Fraction(10, 9)

    def test_does_not_apply_when_shooting(self):
        got = resolve(shooting(def_rules={"Melee Evasion"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


# ---------------------------------------------------------------------------
# Dwarf Guilds army book
# ---------------------------------------------------------------------------


class TestSturdy:
    """Sturdy: +1 to defense rolls when shot or charged from over 9" away."""

    def test_improves_defense_past_nine_inches(self):
        # Defense 3 becomes a 2+, blocked on 5 of 6 faces.
        got = resolve(shooting(def_rules={"Sturdy"}, long_range=True))
        assert got.wounds == Fraction(5) * Fraction(1, 6)

    def test_is_inert_inside_nine_inches(self):
        got = resolve(shooting(def_rules={"Sturdy"}, long_range=False))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_applies_on_a_charge_from_over_nine_inches(self):
        got = resolve(
            melee(melee_state="Charging", def_rules={"Sturdy"}, long_range=True)
        )
        assert got.wounds == Fraction(5) * Fraction(1, 6)

    def test_does_not_apply_in_melee_without_a_charge(self):
        got = resolve(melee(def_rules={"Sturdy"}, long_range=True))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestMeleeSlayer:
    """Melee Slayer: on a charge, AP(+2) if the target has Tough(3) or higher."""

    def test_adds_ap_two_on_a_charge_against_tough_three(self):
        got = resolve(
            melee(melee_state="Charging", att_rules={"Melee Slayer"}, tough=3)
        )
        assert got.wounds == Fraction(10, 3)

    def test_adds_nothing_against_tough_two(self):
        got = resolve(
            melee(melee_state="Charging", att_rules={"Melee Slayer"}, tough=2)
        )
        assert got.wounds == BASE_WOUNDS

    def test_does_not_apply_without_a_charge(self):
        got = resolve(melee(att_rules={"Melee Slayer"}, tough=3))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestCrack:
    """Crack: on unmodified results of 6 to hit, those hits get AP(+2)."""

    def test_natural_sixes_get_ap_two(self):
        expected = H6 * Fraction(4, 6) + Fraction(20, 6) * Fraction(2, 6)
        assert resolve(shooting(att_rules={"Crack"})).wounds == expected

    def test_unlike_rending_it_does_not_bypass_regeneration(self):
        got = resolve(shooting(att_rules={"Crack"}, def_rules={"Regeneration"}))
        without = resolve(shooting(att_rules={"Crack"}))
        assert got.wounds == without.wounds * Fraction(2, 3)


class TestArtillery:
    """Artillery: +1 to hit shooting past 9"; enemies shooting it past 9" get -2 to hit."""

    def test_adds_one_to_hit_shooting_past_nine_inches(self):
        got = resolve(shooting(att_rules={"Artillery"}, long_range=True))
        assert got.hits == Fraction(20, 3)
        assert got.wounds == Fraction(20, 9)

    def test_attacker_bonus_is_inert_inside_nine_inches(self):
        got = resolve(shooting(att_rules={"Artillery"}, long_range=False))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_attacker_bonus_does_not_apply_in_melee(self):
        got = resolve(melee(att_rules={"Artillery"}, long_range=True))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_subtracts_two_from_enemy_hit_rolls_past_nine_inches(self):
        got = resolve(shooting(def_rules={"Artillery"}, long_range=True))
        assert got.hits == Fraction(5, 3)
        assert got.wounds == Fraction(5, 9)

    def test_defender_malus_is_inert_inside_nine_inches(self):
        got = resolve(shooting(def_rules={"Artillery"}, long_range=False))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_defender_malus_does_not_apply_in_melee(self):
        got = resolve(melee(def_rules={"Artillery"}, long_range=True))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


# ---------------------------------------------------------------------------
# Orc Marauders army book
# ---------------------------------------------------------------------------


class TestFerocious:
    """Ferocious: unmodified 6s to hit deal 1 extra hit, in shooting or melee,
    at any range."""

    def test_adds_a_hit_per_natural_six(self):
        got = resolve(shooting(att_rules={"Ferocious"}))
        assert got.hits == Fraction(5) + H6
        assert got.wounds == (Fraction(5) + H6) * Fraction(1, 3)

    def test_applies_in_melee_without_a_charge(self):
        got = resolve(melee(att_rules={"Ferocious"}))
        assert got.hits == Fraction(5) + H6


class TestFerociousBoost:
    """If this model has Ferocious, when it shoots or charges enemies over 9"
    away, naturals 5-6 (instead of only 6) each deal an extra hit."""

    def test_widens_the_bonus_to_naturals_five_and_six_past_nine_inches(self):
        got = resolve(
            shooting(att_rules={"Ferocious", "Ferocious Boost"}, long_range=True)
        )
        assert got.hits == Fraction(5) + 2 * H6
        assert got.wounds == (Fraction(5) + 2 * H6) * Fraction(1, 3)

    def test_is_inert_inside_nine_inches(self):
        """Only plain Ferocious's unconditional bonus applies (via substring match)."""
        got = resolve(
            shooting(att_rules={"Ferocious", "Ferocious Boost"}, long_range=False)
        )
        assert got.hits == Fraction(5) + H6

    def test_does_not_apply_in_melee_without_a_charge(self):
        got = resolve(
            melee(att_rules={"Ferocious", "Ferocious Boost"}, long_range=True)
        )
        assert got.hits == Fraction(5) + H6

    def test_applies_on_a_charge_from_over_nine_inches(self):
        got = resolve(
            melee(
                melee_state="Charging",
                att_rules={"Ferocious", "Ferocious Boost"},
                long_range=True,
            )
        )
        assert got.hits == Fraction(5) + 2 * H6


class TestBadShot:
    """Bad Shot: -1 to hit rolls when shooting."""

    def test_subtracts_one_from_hit_rolls_when_shooting(self):
        got = resolve(shooting(att_rules={"Bad Shot"}))
        assert got.hits == Fraction(10, 3)
        assert got.wounds == Fraction(10, 9)

    def test_does_not_apply_in_melee(self):
        got = resolve(melee(att_rules={"Bad Shot"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestPrecisionChargeAura:
    """Precision Charge Aura: +1 to hit rolls when charging."""

    def test_adds_one_to_hit_rolls_when_charging(self):
        got = resolve(
            melee(melee_state="Charging", att_rules={"Precision Charge Aura"})
        )
        assert got.hits == Fraction(20, 3)
        assert got.wounds == Fraction(20, 9)

    def test_does_not_apply_without_a_charge(self):
        got = resolve(melee(att_rules={"Precision Charge Aura"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS


class TestTear:
    """Tear: against targets where most models have Tough(9) or higher, the
    weapon gets AP(+4). Not gated by charging, unlike Melee Slayer."""

    def test_adds_ap_four_against_tough_nine(self):
        got = resolve(shooting(att_rules={"Tear"}, tough=9))
        assert got.hits == Fraction(5)
        assert got.wounds == Fraction(25, 6)

    def test_adds_nothing_against_tough_eight(self):
        got = resolve(shooting(att_rules={"Tear"}, tough=8))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_applies_in_melee_without_a_charge(self):
        got = resolve(melee(att_rules={"Tear"}, tough=9))
        assert got.wounds == Fraction(25, 6)


# ---------------------------------------------------------------------------
# Prime Brothers army book
# ---------------------------------------------------------------------------


class TestPrecise:
    """Precise: +1 to hit when attacking, shooting or melee."""

    def test_adds_one_to_hit_when_shooting(self):
        got = resolve(shooting(att_rules={"Precise"}))
        assert got.hits == Fraction(20, 3)
        assert got.wounds == Fraction(20, 9)

    def test_adds_one_to_hit_in_melee_too(self):
        got = resolve(melee(att_rules={"Precise"}))
        assert got.hits == Fraction(20, 3)
        assert got.wounds == Fraction(20, 9)


class TestShatter:
    """Shatter: against targets where most models have Tough(3) or higher,
    the weapon gets AP(+2). Not gated by charging, unlike Melee Slayer."""

    def test_adds_ap_two_against_tough_three(self):
        got = resolve(shooting(att_rules={"Shatter"}, tough=3))
        assert got.hits == Fraction(5)
        assert got.wounds == Fraction(10, 3)

    def test_adds_nothing_against_tough_two(self):
        got = resolve(shooting(att_rules={"Shatter"}, tough=2))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS

    def test_applies_in_melee_without_a_charge(self):
        got = resolve(melee(att_rules={"Shatter"}, tough=3))
        assert got.wounds == Fraction(10, 3)


class TestPrimeborn:
    """Primeborn: units where all models have this rule reduce incoming AP by
    1 (min AP(0)) when shot or charged from over 9" away - same gating as
    Sturdy, same maths as Fortified."""

    def test_reduces_incoming_ap_by_one_past_nine_inches(self):
        got = resolve(shooting(ap=2, def_rules={"Primeborn"}, long_range=True))
        assert got.wounds == Fraction(5, 2)

    def test_never_pushes_ap_below_zero(self):
        got = resolve(shooting(def_rules={"Primeborn"}, long_range=True))
        assert got.wounds == BASE_WOUNDS

    def test_is_inert_inside_nine_inches(self):
        got = resolve(shooting(ap=2, def_rules={"Primeborn"}, long_range=False))
        assert got.wounds == Fraction(10, 3)

    def test_applies_on_a_charge_from_over_nine_inches(self):
        got = resolve(
            melee(
                melee_state="Charging",
                ap=2,
                def_rules={"Primeborn"},
                long_range=True,
            )
        )
        assert got.wounds == Fraction(5, 2)

    def test_does_not_apply_in_melee_without_a_charge(self):
        got = resolve(melee(ap=2, def_rules={"Primeborn"}, long_range=True))
        assert got.wounds == Fraction(10, 3)


# ---------------------------------------------------------------------------
# Saurian Starhost army book
# ---------------------------------------------------------------------------


class TestEvasive:
    """Evasive: enemies get -1 to hit rolls when attacking units where all
    models have this rule. Unconditional, unlike Stealth (ranged, past 9")
    or Melee Evasion (melee only)."""

    def test_gives_minus_one_to_hit_when_shooting(self):
        got = resolve(shooting(def_rules={"Evasive"}))
        assert got.hits == Fraction(10, 3)
        assert got.wounds == Fraction(10, 9)

    def test_gives_minus_one_to_hit_in_melee_too(self):
        got = resolve(melee(def_rules={"Evasive"}))
        assert got.hits == Fraction(10, 3)
        assert got.wounds == Fraction(10, 9)


class TestPrimal:
    """Primal: for each unmodified roll of 6 to hit when attacking, this
    model may roll +1 attack with that weapon (resolved at the normal hit
    chance; the rule doesn't apply to the newly generated attacks, so there
    is no further chaining). Predator is worded identically."""

    def test_adds_an_extra_attack_per_unmodified_six(self):
        got = resolve(shooting(att_rules={"Primal"}))
        assert got.hits == Fraction(35, 6)
        assert got.wounds == Fraction(35, 18)

    def test_predator_behaves_exactly_like_primal(self):
        got = resolve(shooting(att_rules={"Predator"}))
        assert got.hits == Fraction(35, 6)
        assert got.wounds == Fraction(35, 18)

    def test_primal_boost_buff_does_not_stand_in_for_plain_primal(self):
        """"Primal Boost Buff" contains "Primal" as a substring but is a
        distinct rule (granting Primal Boost to another unit); it must not
        trigger Primal's extra attack on its own."""
        got = resolve(shooting(att_rules={"Primal Boost Buff"}))
        assert got.hits == Fraction(5)
        assert got.wounds == BASE_WOUNDS
