"""The closed cue tables of the engine's argument rules (rules ``argdiag-2``; design table A.8.4).

Every table is data: a tuple of lower-case phrases, each read into a token sequence by
:func:`epinoic_logic.lexis.cue_table` and matched only through :mod:`epinoic_logic.lexis` (``has_cue`` and
``find_cues``), on word boundaries, in time linear in the gloss or label read. ``*`` in a phrase matches any one token.
Nothing here is evaluated: a gloss (a symbol's ``meaning``) or a label is read as a string, through the shared
tokenizer, and only these tables decide what its words count as.

The tables are English. A gloss in another language matches fewer cues, so it gets fewer warnings, never more: a miss,
never a false alarm. A change to any table changes ``engine.identity.build_id`` (this module is an engine source), so a
result always names the tables that produced its diagnostics. ``tests/engine/test_argument_diagnostics.py`` pins each
table.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..lexis import CueTable, cue_table

__all__ = [
    "UNIVERSAL", "NUMBER_WORDS", "INSTANCE", "SAMPLE", "SAMPLE_PARTICIPLES", "SAMPLING_UNITS", "REPRESENTATIVE", "MEASURE_WORDS", "IRREGULAR_PLURALS", "CAUSAL", "SEQUENCE", "CONTROL",
    "CONTROL_NEGATORS", "TIME_WORDS", "SENSE_QUALIFIERS", "SENSE_EXCLUDED_HEADS", "DEFINITION_DETERMINERS", "DEFINITION_VERBS", "MONTHS",
    "REASON_CONNECTIVES", "MAJORITY", "WRITER_STEP_KINDS", "KNOWLEDGE_KIND", "EquivocalTerm", "EQUIVOCAL_TERMS",
    "NEGATING_WORDS", "NOT_PREFIXED", "DEFINITIONS", "SYNONYM_GROUPS",
    "COMPLEMENTARY_PAIRS", "COMPLEMENTARY_CONTEXT", "EXHAUSTIVE_PARTITIONS", "ORDER_WORDS", "CORRELATION", "COMPARATIVES", "POPULATIONS", "TABLES",
]

#: Open universal quantifiers (hasty generalisation). A cue is NOT open when a number or a number word follows it
#: within three tokens ("all three", "each of the four", "every one"): that is a closed enumeration.
UNIVERSAL: CueTable = cue_table((
    "all", "every", "always", "never", "none", "no one", "nobody", "everyone", "everybody", "everything", "any", "each",
    "in general", "universally", "without exception", "in every case", "in all cases",
))
#: Majority cues (repair round 2, ADV2-10): a claim about most of a population ("most students in the country prefer ...") drawn
#: from a sample is a generalisation like an open universal, unless it keeps the sample's own population (:mod:`.argument`).
MAJORITY: CueTable = cue_table((
    "most", "the majority of", "a majority of", "the vast majority of", "nearly all", "almost all", "in most cases", "generally",
    "usually", "typically",
))
#: Number words that close a universal cue ("all three", "each one", "both").
NUMBER_WORDS: frozenset[str] = frozenset("""
one two three four five six seven eight nine ten eleven twelve twenty thirty forty fifty hundred thousand both
""".split())
#: Cues that a gloss states an instance (one case, one study, one person, a dated event), not a generality. A token with
#: a possessive ("palmer's") or a year also marks an instance (:mod:`.argument`).
INSTANCE: CueTable = cue_table((
    "in this case", "in that case", "in one case", "this", "one", "a", "an", "the study", "this study", "the experiment",
    "the participants", "a participant", "in the study", "in this study", "the sample", "in the sample", "the trial",
))
#: Quantifiers of a sample short of everyone (hasty generalisation, re-run review A-INF-HG): a gloss with one of them
#: states what held for some cases ("some students", "a few schools", "most swans"), not a generality. A gloss that also
#: holds a universal cue ("all three schools") is an enumeration, not a sample (:mod:`.argument`).
SAMPLE: CueTable = cue_table((
    "some", "several", "a few", "few", "a handful", "many", "most", "a number of", "a group of", "a sample of", "a small sample",
    "a minority of", "a majority of", "a couple of", "a pair of", "certain",
))
#: Words that say a fact was found for the cases looked at (hasty generalisation, repair round 2): a sampling participle
#: ("the one quadrat sampled", "the five people interviewed") or a sampling unit ("the quadrat", "the survey").
SAMPLE_PARTICIPLES: frozenset[str] = frozenset("""
sampled surveyed interviewed tested asked questioned polled observed measured studied examined checked visited counted
""".split())
SAMPLING_UNITS: frozenset[str] = frozenset("""
quadrat quadrats transect transects sample samples survey surveys poll polls interview interviews questionnaire questionnaires
plot plots respondent respondents interviewee interviewees
""".split())
#: Words that say a sample was drawn to stand for its population: a fact that says so is no hasty sample.
REPRESENTATIVE: CueTable = cue_table((
    "random", "randomly", "randomised", "randomized", "representative", "stratified", "systematic", "systematically", "census",
))
#: Words after a number that make it a measurement, not a count of cases ("5 metres", "12 per cent", "3 years"): a
#: number followed by a plural noun outside this table counts cases ("two cyclists", "12 participants").
MEASURE_WORDS: frozenset[str] = frozenset("""
per percent percentage cent cents pence penny pounds dollars euros yen degrees metres meters kilometres kilometers miles
centimetres millimetres grams kilograms tonnes tons litres liters seconds minutes hours days weeks months years decades
centuries times points marks units joules watts newtons volts amps ohms pascals moles hertz calories kilojoules kilowatts
mph kph km kg mg ml cm mm hundred thousand million billion trillion dozen pairs feet inches
sessions doses lessons visits rounds sittings attempts repetitions laps
""".split())
#: Plural nouns without a final "s" that count people or things after a number ("two children", "three women").
IRREGULAR_PLURALS: frozenset[str] = frozenset("""
people children men women mice geese teeth cattle sheep fish deer persons staff police clergy
""".split())
#: Causal verbs and phrases (causal leap).
CAUSAL: CueTable = cue_table((
    "caused", "causes", "cause of", "causing", "led to", "leads to", "lead to", "resulted in", "results in", "result of",
    "due to", "because of", "responsible for", "produced", "produces", "brought about", "brings about", "the effect of",
    "effect of", "made * rise", "made * fall", "made * * rise", "made * * fall", "makes * rise", "makes * fall",
    # repair round 2: the verb's plain form ("ice cream sales cause drownings")
    "cause",
    # repair round 3 (ADV3-05, ADV3-07): verbs that say one thing brought another about ("the therapy cured the anxiety")
    "cured", "cures", "healed", "heals", "triggered", "triggers", "sparked", "sparks", "provoked", "provokes", "induced", "induces",
))
#: Cues of a sequence in time (causal leap); "since" counts only before a year, and "then" not after an "if" (the
#: consequent of a conditional is no later time) (:mod:`.argument`).
SEQUENCE: CueTable = cue_table(("after", "then", "following", "subsequently", "afterwards", "before", "later"))
#: Cues that a fact states a correlation, not a sequence in time (causal leap, repair round 2: a cause read into a
#: correlation): "correlated with", "associated with", "tend to", "go together".
CORRELATION: CueTable = cue_table((
    "correlated", "correlates", "correlate", "correlation", "correlations", "associated with", "association between", "association with",
    "linked with", "go together", "goes together", "went together", "rise together", "rose together", "move together", "moved together",
    "tend to", "tends to", "tended to",
))
#: Comparative words. Two of them after a population noun and its relative or "with" clause ("countries that eat more
#: chocolate win more Nobel prizes", "towns with more ice cream sales have more drownings") compare groups in step: a
#: correlation. "earlier" and "later" are no comparatives here (they are time words).
COMPARATIVES: frozenset[str] = frozenset("""
more less fewer higher lower greater larger smaller bigger longer shorter better worse faster slower richer poorer older younger
heavier stronger weaker warmer colder hotter cooler
""".split())
#: Nouns of the units an observation counts (people, places, organisations): a correlation between groups is stated
#: about them, while a property of a physical class ("gases with more energy") is no observation of groups.
POPULATIONS: frozenset[str] = frozenset("""
countries nations states regions areas towns cities villages districts counties neighbourhoods neighborhoods schools universities
students pupils children people adults teenagers men women patients workers employees firms companies businesses households families
consumers customers users participants respondents smokers drinkers drivers hospitals shops stores voters readers viewers players
teams athletes
runners swimmers cyclists competitors members learners volunteers residents citizens visitors tourists investors farmers owners
buyers parents mothers fathers babies infants girls boys teachers doctors nurses commuters shoppers
""".split())
#: Cues that something controls for other causes: one of them in the problem rules a causal leap out, unless it is
#: negated ("there was no control group": :data:`CONTROL_NEGATORS` within the three tokens before it) or, for "compared
#: with" and "compared to", it opens a comparison with an earlier time ("compared with the months before April": a
#: before-and-after comparison is the sequence itself, :data:`TIME_WORDS`) (re-run review ADV-06). A bare "control" is no
#: cue ("the party took control of the press"): only the phrases of a controlled comparison are.
CONTROL: CueTable = cue_table((
    "random", "randomly", "randomised", "randomized", "randomisation", "randomization", "control group", "control groups",
    "control condition", "control sample", "a control", "the control", "controlled trial", "controlled trials", "controlled experiment",
    "controlled experiments", "controlled study", "controlled for", "controlling for", "controls for", "compared with", "compared to",
    "comparison group", "matched", "placebo", "double blind", "double-blind", "blind trial",
))
#: Words that, within the three tokens before a control cue, negate it ("no control group", "without a placebo",
#: "not randomised", "lacked a comparison group").
CONTROL_NEGATORS: frozenset[str] = frozenset({"no", "not", "never", "without", "lacked", "lacking", "lacks", "lack", "absence", "nor", "non"})
#: Words that make "compared with ..." a comparison with another time, not with a control (within four tokens after it).
TIME_WORDS: frozenset[str] = frozenset("""
before after earlier previous prior preceding last ago year years month months week weeks day days period periods decade
decades century quarter quarters season seasons beginning start january february march april may june july august september
october november december yesterday then
""".split())
#: Sense qualifiers: a word that fixes which sense of the noun after it is meant (equivocation). "in the ... sense" and a
#: parenthetical that glosses a sense qualify too; a parenthetical that names a referent (a name, a title, a date or a
#: figure) does not (:mod:`.argument`).
SENSE_QUALIFIERS: frozenset[str] = frozenset({
    "scientific", "everyday", "ordinary", "colloquial", "legal", "technical", "mathematical", "statistical", "literal",
    "figurative", "biological", "economic",
})
#: Words a sense marker can sit on that are never the head noun of the equivocation ("in the everyday sense").
SENSE_EXCLUDED_HEADS: frozenset[str] = frozenset({"sense", "meaning", "use", "usage", "word", "term"})
#: Determiners that open a bare generic definition ("a theory is ...", "every theory is ..."). "the" is not one: "the
#: surge is ..." speaks of one surge and defines nothing.
DEFINITION_DETERMINERS: frozenset[str] = frozenset({"a", "an", "every", "all", "any", "each"})
#: Verbs of a bare generic definition, right after the defined noun.
DEFINITION_VERBS: frozenset[str] = frozenset({"is", "are", "means", "mean", "denotes", "denote", "refers", "refer", "equals"})


@dataclass(frozen=True)
class EquivocalTerm:
    """A word of school subjects with a technical and an everyday sense (equivocation, re-run review A-INF-EQ): its
    forms, and for each sense its name and the cues that select it in a gloss or a label. A cue selects its sense only
    when no negation stands in the three tokens before it ("not necessarily the strongest")."""
    forms: frozenset[str]
    technical: str
    technical_cues: CueTable
    everyday: str
    everyday_cues: CueTable


def _term(forms: str, technical: str, technical_cues: tuple[str, ...], everyday: str, everyday_cues: tuple[str, ...]) -> EquivocalTerm:
    return EquivocalTerm(frozenset(forms.split()), technical, cue_table(technical_cues), everyday, cue_table(everyday_cues))


#: The equivocal terms (closed). ARG-EQ-003 reads a writer's link that uses one of these words in both senses: the
#: technical sense selected in one of its texts (a symbol's meaning, the link's label) and the everyday sense in another,
#: or both in the link's own label ("pushing a wall all day is hard work, so work is done on it"). The cue lists are
#: deliberately specific: a word outside the table, or a gloss with neither sense's cue, is never read as equivocal (a
#: miss, never a false alarm).
EQUIVOCAL_TERMS: tuple[EquivocalTerm, ...] = (
    _term("theory theories", "scientific", (
        "scientific theory", "scientific sense", "in the scientific sense", "well substantiated", "well-substantiated", "substantiated",
        "body of evidence", "tested explanation", "explanation supported", "supported by evidence", "explains a wide range"),
        "everyday", ("guess", "guesses", "hunch", "speculation", "unproven", "untested", "just a theory", "only a theory", "mere theory",
                     "opinion", "everyday sense", "in the everyday sense", "not proven")),
    _term("fittest fitter fitness fit", "biological", (
        "best adapted", "well adapted", "better adapted", "most adapted", "adapted to", "adaptation", "reproductive success", "reproduce",
        "reproduces", "offspring", "pass on", "passes on", "natural selection", "biological sense", "in the biological sense",
        "biological fitness", "suited to", "suited to its environment", "survive and reproduce"),
        "everyday", ("strongest", "stronger", "strength", "physically", "physical strength", "healthiest", "athletic", "muscular", "fastest",
                     "toughest", "biggest", "exercise", "in good shape", "everyday sense", "in the everyday sense", "gym", "cardiovascular",
                     "aerobic", "stamina", "endurance", "physical fitness", "fitness test", "fit and healthy", "trains", "training")),
    _term("work works worked", "physics", (
        "work done", "does work", "do work", "done on", "force times distance", "force multiplied by", "force times displacement",
        "force and displacement", "displacement", "distance moved in the direction", "in the direction of the force", "joule", "joules",
        "energy transferred", "physics sense", "in the physics sense", "scientific sense", "in physics"),
        "everyday", ("hard work", "effort", "tiring", "tired", "tiredness", "exhausting", "exhausted", "labour", "labor", "all day",
                     "sweat", "strain", "job", "everyday sense", "in the everyday sense", "takes effort")),
    _term("power powerful", "physics", (
        "rate of doing work", "rate of energy", "energy transferred per", "work done per", "per second", "watt", "watts", "kilowatt",
        "kilowatts", "physics sense", "in the physics sense"),
        "everyday", ("influence", "authority", "control over", "political power", "in charge", "strength", "everyday sense",
                     "in the everyday sense")),
    _term("energy energetic", "physics", (
        "joule", "joules", "kinetic", "potential energy", "conserved", "conservation of energy", "energy store", "energy transferred",
        "physics sense", "in the physics sense"),
        "everyday", ("enthusiasm", "enthusiastic", "lively", "vigour", "vigor", "feel tired", "feels tired", "full of energy",
                     "everyday sense", "in the everyday sense")),
    _term("significant significance significantly", "statistical", (
        "statistically", "p value", "p-value", "p <", "p<", "probability", "chance alone", "by chance", "significance level",
        "statistical sense", "in the statistical sense", "hypothesis test"),
        "everyday", ("important", "large", "big", "major", "substantial", "matters", "meaningful", "noticeable", "everyday sense",
                     "in the everyday sense")),
    _term("normal normally", "statistical", (
        "normal distribution", "normally distributed", "bell curve", "bell-shaped", "standard deviation", "statistical sense",
        "in the statistical sense"),
        "everyday", ("usual", "typical", "ordinary", "acceptable", "healthy", "natural", "everyday sense", "in the everyday sense")),
    _term("law laws", "scientific", (
        "scientific law", "law of nature", "laws of nature", "physical law", "law of physics", "laws of physics", "describes how",
        "observed regularity", "a regularity", "regularity", "law of demand", "law of supply", "economic law", "scientific sense",
        "in the scientific sense"),
        "legal", ("parliament", "illegal", "court", "courts", "police", "punish", "punished", "punishment", "obey", "obeys", "obeyed", "obeying",
                  "break the law", "broke the law", "breaking the law", "breaks the law", "legal sense", "in the legal sense", "statute", "legislation",
                  "fined", "fine", "sentenced", "enforced", "enforce")),
    _term("depression depressed", "economic", (
        "economic depression", "economy", "economic", "unemployment", "output fell", "gdp", "recession", "economic sense",
        "in the economic sense"),
        "clinical", ("mental", "mood", "sad", "sadness", "illness", "clinical", "therapy", "medication", "clinical sense",
                     "in the clinical sense")),
    _term("demand", "economic", (
        "quantity demanded", "willing and able", "demand curve", "at each price", "economic sense", "in the economic sense",
        # repair round 2: effective demand, desire backed by the ability to pay
        "effective demand", "willingness and ability", "ability to pay", "able to pay", "purchasing power", "backed by"),
        "everyday", ("insisted", "insists", "insist", "demanded that", "ordered", "required them", "everyday sense",
                     "in the everyday sense",
                     # repair round 2: demand read as wanting, with no ability to pay
                     "want", "wants", "wanted", "desire", "desires", "wish", "wishes", "would like", "would love")),
    _term("adaptation adaptations adapted", "evolutionary", (
        "over generations", "over many generations", "inherited", "natural selection", "population", "evolutionary sense",
        "in the evolutionary sense", "gene", "genes", "allele", "alleles"),
        "individual", ("during its life", "during their lives", "in its lifetime", "learned", "got used to", "gets used to", "individual",
                       "acclimatised", "acclimatized", "practice")),
    _term("light lights", "physics", (
        "electromagnetic", "radiation", "photon", "photons", "wavelength", "emits light", "emit light", "gives off light", "give off light",
        "visible light", "speed of light", "physics sense", "in the physics sense",
        # light as what travels or is refracted (repair round 4, ADV4-08 b: "light travels at 3.0 × 10⁸ m s⁻¹" gives the sense by
        # a figure, which the tokens do not keep); "a light car travels at" puts a noun between, so it selects nothing
        "light travels", "light travel", "light travelled", "light traveled", "light moves", "light is refracted", "light is reflected",
        "ray of light", "rays of light", "light ray", "light rays", "beam of light", "light beam", "light beams", "light wave", "light waves"),
        "everyday", ("small mass", "little mass", "low mass", "weighs little", "not heavy", "lightweight", "light in weight", "easy to lift",
                     "everyday sense", "in the everyday sense")),
    _term("organic", "chemical", (
        "carbon compound", "carbon compounds", "contains carbon", "hydrocarbon", "hydrocarbons", "carbon atoms", "chemical sense",
        "in the chemical sense"),
        "farming", ("pesticide", "pesticides", "farming", "farmed", "grown without", "free range", "free-range", "natural", "healthy",
                    "chemical-free")),
)

# ----------------------------------------------------------------------------------------------- paraphrase tables
# Circular reasoning by paraphrase (ARG-CIRC-003, re-run review A-INF-CIRC): a reason that restates the point in other
# words: another voice or tense ("his ambition drives him" / "he is driven by ambition"), another part of speech
# ("lacked political stability" / "was politically unstable"), both read by the shared root reader
# (:func:`epinoic_logic.lexis.root`), a negating word for a negating prefix, or a closed definition or synonym of an
# evaluative word ("achieved what it set out to achieve" / "was successful").

#: Words that negate what follows them as a negating prefix does ("lacked stability" / "unstable").
NEGATING_WORDS: frozenset[str] = frozenset({"lack", "lacks", "lacked", "lacking", "absence", "absent", "without", "fail", "fails", "failed",
                                            "failing"})
#: A negating prefix (:data:`epinoic_logic.lexis.NEGATING_PREFIXES`) negates a word when the rest of it is a word of the
#: other text ("unstable" against "stability"), or, for "un" and "non", when the rest has at least four letters and the
#: word does not open with one of these.
NOT_PREFIXED: tuple[str, ...] = ("under", "uni", "until", "unless", "unanim", "uncle", "union")
#: Closed definitions of evaluative words: the head word and the word sets of its definitions, each word read through
#: the same root reader as the texts (:func:`epinoic_logic.lexis.root`); a text holding every word of one definition reads as the head
#: ("achieved what it set out to achieve" holds "achieve" and "set").
DEFINITIONS: dict[str, tuple[tuple[str, ...], ...]] = {
    "success": tuple(tuple(x.split()) for x in (
        "achieve aims", "achieve goals", "achieve objectives", "achieve set", "achieve intended", "achieve targets", "achieve purpose",
        "accomplish aims", "accomplish goals", "accomplish set", "meet aims", "meet goals", "meet targets", "meet objectives",
        "fulfil aims", "fulfil goals", "fulfill aims", "fulfill goals")),
    "effective": tuple(tuple(x.split()) for x in (
        "achieve intended result", "achieve desired result", "produce intended result", "produce desired result",
        "achieve intended outcome", "produce intended effect", "produce desired effect", "work intended")),
    "reliable": tuple(tuple(x.split()) for x in ("trust", "trusted", "depend", "depended")),
    "flood": tuple(tuple(x.split()) for x in ("overflow bank", "burst bank", "overflow banks", "burst banks", "water cover land")),
}
#: Synonym groups of evaluative and change words, each read as its first member (through the same root reader).
SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("important", "significant", "crucial", "major", "importance", "significance"),
    ("necessary", "essential", "required", "needed", "necessity"),
    ("dangerous", "hazardous", "risky", "danger"),
    ("harmful", "damaging", "harm", "damage"),
    ("beneficial", "advantageous", "benefit", "advantage"),
    ("increase", "rise", "grow", "growth", "increased", "rose", "grew"),
    ("decrease", "fall", "decline", "drop", "decreased", "fell", "declined", "dropped"),
    ("large", "big", "huge"),
    ("weak", "feeble", "weakness"),
    ("cheap", "inexpensive"),
    # a measure that works is effective, one that did not work is ineffective (repair round 4, ADV4-08 c)
    ("effective", "work", "works", "worked", "effectual"),
    ("often", "frequently", "frequent", "regularly", "repeatedly"),
    ("rarely", "seldom", "infrequently", "infrequent"),
    ("quickly", "rapidly", "rapid", "quick", "swiftly", "swift"),
    ("rich", "wealthy", "affluent", "wealth"),
    ("poor", "impoverished", "poverty"),
    ("begin", "start", "commence", "began", "started", "beginning"),
    # repair round 5 (ADV5-15 c): an evaluation restated in another word ("boring because it is tedious")
    ("boring", "tedious", "dull", "monotonous"),
)

#: Option words that exclude each other and cover every case (false dilemma, re-run review ADV-13): two options whose
#: meanings are the same but for one such pair are complementary ("n is even" / "n is odd"). A pair under a context
#: word holds only where a meaning holds that word ("0" / "1" for a bit).
COMPLEMENTARY_PAIRS: frozenset[frozenset[str]] = frozenset(frozenset(p.split()) for p in (
    "even odd", "true false", "alive dead", "rational irrational", "finite infinite", "possible impossible", "present absent",
    "legal illegal", "guilty innocent", "on off", "open closed", "valid invalid", "pass fail", "yes no", "positive nonpositive",
    "convergent divergent", "converge diverge",
))
COMPLEMENTARY_CONTEXT: dict[frozenset[str], frozenset[str]] = {
    frozenset({"0", "1"}): frozenset({"bit", "bits", "binary", "boolean"}),
}
#: Sets of options that exhaust what they speak of (false dilemma, repair round 3, ADV3-04): an either/or whose options are
#: the same words but for one slot each of one of these sets, every slot taken once, is exhaustive ("x is positive, negative
#: or zero", "the trolley is moving or at rest", "the reaction is exothermic or endothermic"). Each slot lists the phrases
#: that fill it, read through the shared root reader. A set with a slot left out ("prices rose or fell") is no partition.
EXHAUSTIVE_PARTITIONS: tuple[tuple[tuple[str, ...], ...], ...] = (
    (("positive",), ("negative",), ("zero", "0")),
    (("acute",), ("right", "right angled", "right-angled", "a right angle"), ("obtuse",)),
    (("increased", "increase", "increases", "rose", "rise", "rises", "risen", "went up", "grew", "grow", "grows"),
     ("decreased", "decrease", "decreases", "fell", "fall", "falls", "fallen", "went down", "declined", "decline", "dropped", "drop"),
     ("stayed the same", "stays the same", "remained the same", "remains the same", "stayed constant", "remained constant", "unchanged",
      "stayed unchanged", "remained unchanged", "did not change", "does not change", "constant")),
    (("prime",), ("composite",), ("1", "one", "neither prime nor composite")),
    (("moving", "in motion"), ("stationary", "at rest", "not moving", "still")),
    (("heads",), ("tails",)),
    (("acidic", "acid"), ("neutral",), ("alkaline", "basic", "alkali")),
    (("accepted",), ("rejected",)),
    (("reflected",), ("absorbed",), ("transmitted",)),
    (("exothermic",), ("endothermic",)),
    (("solid",), ("liquid",), ("gas", "gaseous")),
    (("won", "win", "wins"), ("lost", "lose", "loses"), ("drew", "draw", "draws", "drawn")),
    (("even",), ("odd",)),
)
#: Comparisons written in words, read as IR order operators for the options of an either/or ("x is greater than 3 or x is at
#: most 3": repair round 3, ADV3-04). Longest phrases first.
ORDER_WORDS: tuple[tuple[str, str], ...] = (
    ("greater than or equal to", "ge"), ("less than or equal to", "le"), ("more than or equal to", "ge"), ("no more than", "le"),
    ("no less than", "ge"), ("not more than", "le"), ("not less than", "ge"), ("not greater than", "le"), ("not equal to", "ne"),
    ("greater than", "gt"), ("more than", "gt"), ("larger than", "gt"), ("bigger than", "gt"), ("higher than", "gt"), ("above", "gt"),
    ("less than", "lt"), ("fewer than", "lt"), ("smaller than", "lt"), ("lower than", "lt"), ("below", "lt"), ("at least", "ge"),
    ("at most", "le"), ("equal to", "eq"), ("equals", "eq"), ("exactly", "eq"),
)
#: Month names: with years, the date tokens a "same quantity at two times" comparison may differ by.
MONTHS: frozenset[str] = frozenset("""
january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec
""".split())
#: Reason connectives: the words that offer what precedes or follows them as a reason ("because" counts only when "of"
#: does not follow it: "because of" is a cause phrase, not a reason clause). The claim and report rules and the
#: translator's encoding flags read the same table (``translate.diag_argument``).
REASON_CONNECTIVES: CueTable = cue_table((
    "because", "since", "so", "therefore", "thus", "hence", "given that", "due to the fact that", "which shows", "which means",
    "which suggests", "which proves", "this shows", "this means", "this suggests", "as shown by", "as seen in", "as demonstrated by",
    "as evidenced by", "as * shows", "as * suggests", "as * * shows", "as * * suggests", "as * * * shows", "as * * * suggests",
    "as * show", "as * * show", "consequently", "it follows that",
))
#: The grounding kind of a fact the writer states from subject knowledge. A restatement made only of such facts, with no
#: reason offered for it, transcribes a bare factual statement: ARG-CIRC-001 records it at info, never as a circle.
KNOWLEDGE_KIND = "general_knowledge"
#: Grounding kinds that mark a premise as the writer's own step (``None`` stands for no grounding). A link of another
#: kind that no check established is still a writer's link for R0 (ARG-LINK-001), but the pattern rules that accuse a
#: step of a fallacy (affirming the consequent, denying the antecedent, false dilemma, hasty generalisation, causal
#: leap, equivocation by definition) read only these: a rule the writer states from subject knowledge or a relation
#: labelled with a source is not the writer's inference.
WRITER_STEP_KINDS: frozenset = frozenset({"specialist_inference", "assumption", None})

#: Every table by name, for the tests that pin them.
TABLES: dict[str, object] = {
    "universal": UNIVERSAL, "number_words": NUMBER_WORDS, "instance": INSTANCE, "sample": SAMPLE, "measure_words": MEASURE_WORDS,
    "irregular_plurals": IRREGULAR_PLURALS, "causal": CAUSAL, "sequence": SEQUENCE, "control": CONTROL, "control_negators": CONTROL_NEGATORS,
    "time_words": TIME_WORDS, "sense_qualifiers": SENSE_QUALIFIERS, "sense_excluded_heads": SENSE_EXCLUDED_HEADS,
    "definition_determiners": DEFINITION_DETERMINERS, "definition_verbs": DEFINITION_VERBS, "months": MONTHS,
    "reason_connectives": REASON_CONNECTIVES, "majority": MAJORITY, "writer_step_kinds": WRITER_STEP_KINDS, "equivocal_terms": EQUIVOCAL_TERMS,
    "negating_words": NEGATING_WORDS,
    "not_prefixed": NOT_PREFIXED, "definitions": DEFINITIONS, "synonym_groups": SYNONYM_GROUPS,
    "complementary_pairs": COMPLEMENTARY_PAIRS, "complementary_context": COMPLEMENTARY_CONTEXT,
    "correlation": CORRELATION, "comparatives": COMPARATIVES, "populations": POPULATIONS,
    "sample_participles": SAMPLE_PARTICIPLES, "sampling_units": SAMPLING_UNITS, "representative": REPRESENTATIVE,
    "exhaustive_partitions": EXHAUSTIVE_PARTITIONS, "order_words": ORDER_WORDS,
}
