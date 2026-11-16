"""Texts of the clearance c3 (arena round 10) fix stage for the prose arithmetic, the calendar lengths and the figures taken from supplied
texts: each fault as the adversarial lens wrote it beside the genuine sentence it changed. Every expected value is fixed here, never taken
from the reader under test. The supplied texts are short practice texts written for these tests (the businesses, places and figures are
fictional).
"""
from __future__ import annotations

#: (id, faulty sentence, genuine sentence): prose arithmetic decided by the worked reader on every prose branch.
PROSE_ARITHMETIC = [
    ("ll-arith", "Your target of about 900 words would fall 400 words below the 1,200-word minimum, which usually costs marks.",
     "Your target of about 900 words would fall 300 words below the 1,200-word minimum, which usually costs marks."),
    ("ec-fleet", "Quotas can be sold, so they concentrate in a few companies, and the fleet fell from 412 to 236 boats (−57.28%).",
     "Quotas can be sold, so they concentrate in a few companies, and the fleet fell from 412 to 236 boats (−42.72%)."),
    ("bm-share", "Option 1 costs $380,000, which is 131.1% of the 2025 profit before interest and tax ($380,000 ÷ $336,000 × 100).",
     "Option 1 costs $380,000, which is 113.1% of the 2025 profit before interest and tax ($380,000 ÷ $336,000 × 100)."),
    ("ps-pct", "Eleven of the 46 students allocated to the app (32.9%) stopped before week 6.",
     "Eleven of the 46 students allocated to the app (23.9%) stopped before week 6."),
    ("ge-share", "It killed 185 people, more than 130 of them (about 85%) in the collapse of two buildings.",
     "It killed 185 people, more than 130 of them (about 70%) in the collapse of two buildings."),
    ("ge-diff", "Haiti's 7.0 and Darfield's 7.1 differ by 0.3 in magnitude.", "Haiti's 7.0 and Darfield's 7.1 differ by 0.1 in magnitude."),
]

#: The two costs a cost difference is read against (bm-cheaper), and the differences stated after them.
OPTION_COSTS = ("Option 1 costs $380,000, which is 113.1% of the 2025 profit. Option 2 costs $290,000, which is 86.3% of that profit. ")
COST_DIFFERENCES = [
    ("Option 2 is $110,000 cheaper, and its outlay is less than a full year's profit.", "COUNTEREXAMPLE"),
    ("Option 2 is $90,000 cheaper, and its outlay is less than a full year's profit.", "ENTAILED"),
    ("Option 1 is $90,000 more expensive than Option 2.", "ENTAILED"),
    ("Option 1 costs $100,000 more than Option 2.", "COUNTEREXAMPLE"),
    ("Option 1 costs $90,000 more than Option 2.", "ENTAILED"),
    ("Option 2 is about $90,000 cheaper.", "ENTAILED"),
]

#: Worked lines the Psychology and Economics branches decide ('=' and '≈' chains, a currency prefix such as 'P$').
WORKED_LINES = [
    ("Psychology", "psychology-specialist", "The starting scores were similar, so the difference in change, 4.5 − 0.6 = 4.9 points, is unlikely to be chance.",
     "The starting scores were similar, so the difference in change, 4.5 − 0.6 = 3.9 points, is unlikely to be chance."),
    ("Psychology", "psychology-specialist", "This is about 1.3 times the standard deviation of about 2.9 (3.7 ÷ 2.9 ≈ 1.8), so the difference is large.",
     "This is about 1.3 times the standard deviation of about 2.9 (3.7 ÷ 2.9 ≈ 1.3), so the difference is large."),
    ("Economics", "economics-specialist", "Value = 48,000 × P$2,150 = P$130,200,000",
     "Value = 48,000 × P$2,150 = P$103,200,000"),
]

#: Stated lengths of time against their spans (quant), each with its expected status.
CALENDAR_LENGTHS = [
    ("The war lasted from July 1936 to April 1939, almost four years.", "COUNTEREXAMPLE"),
    ("The war lasted from July 1936 to April 1939, nearly three years.", "ENTAILED"),
    ("The war lasted from July 1936 to April 1939, almost three years.", "ENTAILED"),
    ("The war lasted from July 1936 to April 1939, more than three years.", "COUNTEREXAMPLE"),
    ("The war lasted from July 1936 to April 1939, more than two years.", "ENTAILED"),
    ("The war lasted from July 1936 to April 1939, less than three years.", "ENTAILED"),
    ("War Communism lasted about five years (1918–1921).", "COUNTEREXAMPLE"),
    ("War Communism lasted about three years (1918–1921).", "ENTAILED"),
    ("War Communism lasted about three years (1918–21).", "ENTAILED"),
    ("The dictator ruled for nearly twenty years (1924–1953).", "COUNTEREXAMPLE"),
    ("The dictator ruled for nearly thirty years (1924–1953).", "ENTAILED"),
]

#: An earthquake dated in one paragraph, and a length after it stated in another (ge-months).
QUAKE_DATED = ("By contrast, the magnitude 7.1 Darfield earthquake struck at 4.35 am on 4 September 2010, about 10 km deep. Comparing Haiti in "
               "2010 with the Darfield earthquake in New Zealand, also in 2010, suggests that development matters.\n\n")
NAMED_LENGTHS = [
    (QUAKE_DATED + "About seven months after Darfield, on 22 February 2011, a magnitude 6.2 aftershock struck near the city.", "COUNTEREXAMPLE"),
    (QUAKE_DATED + "About six months after Darfield, on 22 February 2011, a magnitude 6.2 aftershock struck near the city.", "ENTAILED"),
    (QUAKE_DATED + "Less than six months after Darfield, on 22 February 2011, a magnitude 6.2 aftershock struck near the city.", "ENTAILED"),
    ("About seven months after the Darfield earthquake of 4 September 2010, on 22 February 2011, an aftershock struck.", "COUNTEREXAMPLE"),
]

#: A supplied table with two columns whose ratio an answer states (ec-perboat).
FISHERY_DOC = ("doc-fishery", "A cod fishery (practice text and data written for these tests)", "Test data",
               "A fictional cod fishery.\n\nTable 1: The fishery, selected years\n\n"
               "Year | Catch (thousand tonnes) | Average price (P$ per tonne) | Number of boats | Breeding stock (thousand tonnes)\n"
               "2019 | 48.0 | 2,150 | 412 | 96\n2022 | 31.5 | 2,640 | 305 | 104\n2025 | 36.0 | 2,880 | 236 | 131")
PER_BOAT_WRONG = "Catch per boat rose from about 125.0 tonnes in 2019 to about 152.5 tonnes in 2025."
PER_BOAT_RIGHT = "Catch per boat rose from about 116.5 tonnes in 2019 to about 152.5 tonnes in 2025."

#: A case study whose figures an answer credits to it (bm-case).
TOY_CASE_DOC = ("doc-toys", "A toy maker (case study written for these tests)", "Test data",
                "A fictional toy maker.\n\nThe firm makes wooden trains and puzzles in a converted mill. It sells through its own website and 46 "
                "independent shops, and it employs 28 people.\n\nExtract from the accounts for 2025 ($)\nSales revenue: 2,400,000\nCost of sales: 960,000")
CASE_FIGURES_WRONG = "Compare them with the firm's own figures: sales of $2,400,000 and 32 employees."
CASE_FIGURES_RIGHT = "Compare them with the firm's own figures: sales of $2,400,000 and 28 employees."
