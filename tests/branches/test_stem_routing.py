"""Routing of STEM subjects to the three STEM branches (docs/STEM_DESIGN.md, section 10): aliases on word boundaries,
the STEM aliases, the ``stem`` profile, every display name, the generic fallback and the composition of each branch."""
from __future__ import annotations

import pytest

from epinoic_logic.adapters.stem_specialist import StemTextParser
from epinoic_logic.branches import default_registry
from epinoic_logic.branches.hub import RouterHub
from epinoic_logic.branches.quant import GENERAL
from epinoic_logic.branches.stem_pack import StemPack
from epinoic_logic.stem.hub_hooks import STEM_HOOKS
from epinoic_logic.stem.si_reading import SI_READING
from epinoic_logic.translate.subjects import PROFILES, UNKNOWN, resolve_profile

STEM_BRANCH = {"physics": "sciences", "chemistry": "sciences", "biology": "sciences", "ess": "sciences", "sports_science": "sciences",
               "design_technology": "sciences", "stem": "sciences", "mathematics_aa": "mathematics", "mathematics_ai": "mathematics",
               "mathematics": "mathematics", "computer_science": "computer_science"}


@pytest.mark.parametrize("label,profile", [
    ("Physics", "physics"), ("Physics HL", "physics"), ("IB Physics SL", "physics"), ("Phys", "physics"),
    ("Chemistry", "chemistry"), ("Chem", "chemistry"), ("Chemistry: Part 2", "chemistry"),
    ("Biology", "biology"), ("Bio", "biology"),
    ("ESS", "ess"), ("Environmental Systems and Societies", "ess"), ("Environmental science", "ess"), ("Environmental systems", "ess"),
    ("Sports, Exercise and Health Science", "sports_science"), ("SEHS", "sports_science"), ("Design Technology", "design_technology"),
    ("CS", "computer_science"), ("Comp Sci", "computer_science"), ("Computer Sci", "computer_science"), ("Software engineering", "computer_science"),
    ("Computer Science HL", "computer_science"),
    ("Statistics", "mathematics_ai"), ("Stats", "mathematics_ai"),
    ("Maths: AA", "mathematics_aa"), ("Math: AA", "mathematics_aa"), ("Mathematics: AA", "mathematics_aa"), ("AA HL", "mathematics_aa"), ("AA SL", "mathematics_aa"),
    ("Maths: AI", "mathematics_ai"), ("Math: AI", "mathematics_ai"), ("Mathematics: AI", "mathematics_ai"), ("AI HL", "mathematics_ai"), ("AI SL", "mathematics_ai"),
    ("Mathematics AA", "mathematics_aa"), ("Math AA SL", "mathematics_aa"), ("Maths AI", "mathematics_ai"),
    ("Mathematics: Analysis and Approaches HL", "mathematics_aa"), ("Mathematics: Applications and Interpretation", "mathematics_ai"),
    ("Further Mathematics", "mathematics_aa"), ("Mathematics", "mathematics"), ("Maths", "mathematics"),
    ("Science", "stem"), ("Sciences", "stem"), ("General science", "stem"), ("STEM", "stem"), ("Engineering", "stem"),
    ("Physics/Chemistry", "stem"), ("Biology and Chemistry HL", "stem"), ("Physics, Chemistry and Biology", "stem"),
])
def test_stem_aliases_resolve_and_route(label, profile):
    p = resolve_profile(label)
    assert p.key == profile, (label, p.key)
    assert default_registry().for_subject(label)[0].key == STEM_BRANCH[profile]


@pytest.mark.parametrize("label", ["Assessment", "Process", "Stress and Wellness", "Free fall", "Underwater Basket Weaving", "Processes of change"])
def test_aliases_match_on_word_boundaries_only(label):
    # before word boundaries: 'ess' inside 'Assessment', 'Process', 'Stress'; 'ee' inside 'Free'
    assert resolve_profile(label) is UNKNOWN
    assert default_registry().for_subject(label)[0].key == "generic"


def test_every_display_name_resolves_to_its_own_profile():
    for key, profile in PROFILES.items():
        assert resolve_profile(profile.display_name) is profile, key
        assert resolve_profile(profile.display_name + " HL") is profile, key
        assert resolve_profile(profile.display_name + " SL") is profile, key
    assert resolve_profile("Sports Exercise and Health Science SL").key == "sports_science"
    assert resolve_profile("Spanish A: Literature").key == "language_a_other"


def test_a_single_science_with_a_generic_science_word_is_that_science():
    # 'science' is a stem alias, but a label naming one science resolves to it (longest match), never to stem
    assert resolve_profile("Sports Science").key == "sports_science"
    assert resolve_profile("Computer Science and Physics").key == "computer_science"


def test_unknown_and_missing_subjects_fall_back_to_generic():
    r = default_registry()
    for label in (None, "", "Underwater Basket Weaving", "Free fall"):
        assert r.for_subject(label)[0].key == "generic"


def test_non_stem_routing_is_unchanged():
    r = default_registry()
    assert r.for_subject("History HL")[0].key == "history" and r.for_subject("Economics")[0].key == "economics"
    assert r.for_subject("English A: Language and Literature")[0].key == "english" and r.for_subject("Psychology SL")[0].key == "psychology"
    assert r.for_subject("Business Management HL")[0].key == "business_management" and r.for_subject("Global Politics")[0].key == "history"


def test_stem_branches_are_composed_as_designed():
    r = default_registry()
    assert {"sciences", "mathematics", "computer_science"} <= set(r.keys())
    for key, mode, agent in (("sciences", "sciences", "science-specialist"), ("mathematics", "mathematics", "maths-specialist"),
                             ("computer_science", "computer_science", "cs-specialist")):
        b = r.get(key)
        assert b.packs[0].name == "core" and b.packs[0].reading is SI_READING
        assert isinstance(b.packs[1], StemPack) and b.packs[1].mode == mode and len(b.packs) == 2
        assert b.hub_hooks is STEM_HOOKS
        parser = b.parser()
        assert isinstance(parser, StemTextParser) and parser.agent_id == agent and parser.mode == mode and parser.accepts_request_text
    assert set(r.get("sciences").profile_keys) == {"physics", "chemistry", "biology", "ess", "sports_science", "design_technology", "stem"}
    assert set(r.get("mathematics").profile_keys) == {"mathematics_aa", "mathematics_ai", "mathematics"}
    assert r.get("computer_science").profile_keys == ("computer_science",)


def test_non_stem_branches_keep_the_general_core_pack_and_no_hooks():
    r = default_registry()
    for key in ("english", "history", "psychology", "economics", "business_management", "generic"):
        b = r.get(key)
        assert b.packs[0].name == "core" and b.packs[0].reading is GENERAL and b.hub_hooks is None


def test_the_hub_reports_the_stem_branches():
    hub = RouterHub(signing_key=b"routing-test-key-0123456789abcdef")
    assert hub.branch_for("Physics") == "sciences" and hub.branch_for("Chemistry") == "sciences"
    assert hub.branch_for("Mathematics: Analysis and Approaches") == "mathematics" and hub.branch_for("Computer Science") == "computer_science"
    assert hub.branch_for("Underwater Basket Weaving") == "generic"
