"""NLU front end of the copilot: intent and entities from a typed question, using rules and a gazetteer.

No language model is used here. It reuses the text pipeline from M1: cleaning, sentence splitting, tokens,
stop words (negations kept), POS candidates, fuzzy dish matching and rule based entity recognition.
The intent decides which plain Python code runs next; the language model never chooses that.
"""

import re
from dataclasses import dataclass, field
from datetime import date as Date
from datetime import timedelta

from feedforward.data import nlp_text as T
from feedforward.data.nlp_entities import WEEKDAYS, candidate_entities, extract_entities, split_sentences

INTENTS = ("explain_dish", "explain_range", "whatif_attendance", "whatif_weather", "whatif_special_day",
           "explain_week", "summarise_surplus_risk", "out_of_scope")

UP_WORDS = ("rise", "rises", "increase", "increases", "more", "higher", "up", "grow", "grows", "jump", "jumps", "plus", "extra")
DOWN_WORDS = ("drop", "drops", "fall", "falls", "fewer", "less", "decrease", "decreases", "lower", "down", "reduce",
              "reduces", "decline", "dip", "dips", "minus", "shrinks")
NEGATORS = {"no", "not", "without", "never", "nor", "isn't", "wont", "won't", "doesn't", "dont", "don't"}
HOT_TEMP_C = 38.0  # what "a hot day" means in a what if

ACTION = re.compile(r"^\s*(please\s+)?(approve|send back|change|set|update|order|cancel|cook|prepare|reduce|increase|raise|lower|"
                    r"delete|save|submit)\b")
HYPOTHETICAL = re.compile(r"\b(what if|suppose|assume|imagine|in case|what happens if|what would happen|if)\b"
                          r"|\b(what does|how does|how would|effect of|impact of|what do)\b.*\b(do|change|affect|effect)\b"
                          r"|\b(effect|impact)\b")
RANGE_WORDS = re.compile(r"\b(range|p10|p50|p90|low end|high end|likely|uncertain|uncertainty|confidence|how sure|how certain|"
                         r"band|spread|margin)\b")
RISK_WORDS = re.compile(r"\b(surplus|waste|wastage|leftover|leftovers|overproduc\w*|overcook\w*|spoil\w*|at risk|risk)\b")
WEEK_WORDS = re.compile(r"\b(week|trend|peak|summar\w+|rise|rises|highest|lowest|busiest|quietest|next days|coming days)\b")
WHY_WORDS = re.compile(r"\b(why|explain|usual plan|above|below|higher|lower|more than|less than|compare)\b")
PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per cent)")
# A message that is only a greeting or a thank you gets a short hello with example questions.
GREETING = re.compile(r"^\s*(hi+|hello|hey+|hiya|namaste|good (morning|afternoon|evening)|thanks|thank you|thx|ok|okay)"
                      r"(\s+(there|copilot|team|all))?\s*[!.?]*\s*$")
# Planning questions: what to cook, how much to make. They are answered with the slot's plan against the usual plan.
PLAN_WORDS = re.compile(r"\b(what (should|shall|do|can|would) (i|we) (cook|make|prepare|plan|serve)|what to (cook|make|prepare|plan|serve)"
                        r"|how (much|many)|(the|today'?s|tomorrow'?s|this|our|my) plan|plan for|quantit(y|ies)|portions)\b")
# Words that never name a dish on their own, so they are skipped when looking for part of a dish name.
NOT_DISH_WORDS = {"much", "many", "make", "cook", "plan", "lunch", "dinner", "snacks", "breakfast", "should", "today",
                  "tomorrow", "week", "what", "with", "need", "portions", "quantity", "would", "could", "there", "about"}


@dataclass
class Understanding:
    """What the copilot understood from one question."""

    question: str
    intent: str
    reason: str = ""                       # why a question is out of scope
    dish_ids: list[str] = field(default_factory=list)
    slot: str | None = None
    day_words: list[str] = field(default_factory=list)   # weekday names, "today", "tomorrow" or an ISO date
    pct: float | None = None               # signed attendance change in percent
    weather_type: str | None = None
    temp_max_c: float | None = None
    flags: dict = field(default_factory=dict)            # special_day, exam_week, festival -> True or False
    entities: list[dict] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)
    extra_questions: int = 0


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _negated(tokens: list[str], index: int, window: int = 3) -> bool:
    """True when a negation word appears just before the word at `index` ("no rain", "does not rain")."""
    return any(t in NEGATORS for t in tokens[max(0, index - window):index])


def _weather_from_text(tokens: list[str], ents) -> tuple[str | None, float | None]:
    """Weather type (or a hot day temperature) asked about, with negation kept ("no rain" means dry)."""
    kinds = [e for e in ents if e.type == "WEATHER"]
    if not kinds:
        return None, None
    word = kinds[0].text
    idx = tokens.index(word) if word in tokens else 0
    value = kinds[0].value
    if value == "Hot":
        return (None, None) if _negated(tokens, idx) else (None, HOT_TEMP_C)
    if _negated(tokens, idx) and value in ("Rain", "Drizzle", "Thunder"):
        return "Dry", None
    if value == "Rain" and any(t.startswith("heav") for t in tokens):
        return "Heavy Rain", None
    if value == "Rain" and "light" in tokens:
        return "Light Rain", None
    return value, None


def _pct_from_text(low: str, tokens: list[str]) -> float | None:
    """Signed attendance change: "rises 15%" is +15, "drops by 10 percent" is -10."""
    m = PERCENT_RE.search(low)
    if not m:
        return None
    value = float(m.group(1))
    down = any(w in tokens for w in DOWN_WORDS)
    up = any(w in tokens for w in UP_WORDS)
    return -value if down and not up else value


def _flags_from_text(tokens: list[str], ents) -> dict:
    """Exam week, festival or special day asked about; a negation switches it off."""
    flags = {}
    key = {"exam_week": "exam_week", "festival": "festival", "holiday": "special_day"}
    for e in ents:
        if e.type != "EVENT":
            continue
        first = e.text.split()[0]
        idx = tokens.index(first) if first in tokens else 0
        flags[key[e.value]] = not _negated(tokens, idx)
    return flags


def _partial_dishes(tokens: list[str], dish_keys: dict[str, str]) -> list[str]:
    """Dishes whose name contains a word of the question ("rice" -> steamed rice, jeera rice, ...), at most eight.
    Used only for planning and "why" questions; the context then explains the first of them on that day's menu."""
    found: list[str] = []
    for t in tokens:
        if len(t) < 4 or t in NOT_DISH_WORDS:
            continue
        ids = {dish for key, dish in dish_keys.items() if t in key.split()}
        if 0 < len(ids) <= 8:
            found += sorted(i for i in ids if i not in found)
    return found


def understand(question: str, dish_keys: dict[str, str]) -> Understanding:
    """Intent and entities for one typed question. dish_keys maps match keys to dish ids (the gazetteer)."""
    text = T.clean_text(question)
    sentences = split_sentences(question)
    questions = [s for s in sentences if s.strip().endswith("?")] or sentences[:1]
    focus = (questions or [text])[0]            # the first question is answered; the rest are counted
    low, toks = T.clean_text(focus).lower(), _tokens(focus)
    ents = extract_entities(focus, dish_keys)
    u = Understanding(question=question, intent="out_of_scope", sentences=sentences,
                      extra_questions=max(0, len(questions) - 1),
                      entities=[{"type": e.type, "text": e.text, "value": e.value} for e in ents])
    u.dish_ids = [e.value for e in ents if e.type == "DISH"]
    slots = [e.value for e in ents if e.type == "MEAL_SLOT"]
    u.slot = slots[0] if slots else None
    u.day_words = [str(e.value if e.type == "DATE" and not isinstance(e.value, int) else e.text)
                   for e in ents if e.type in ("WEEKDAY", "DATE")]
    u.pct = _pct_from_text(low, toks)
    u.weather_type, u.temp_max_c = _weather_from_text(toks, ents)
    u.flags = _flags_from_text(toks, ents)

    if GREETING.search(low):
        u.reason = "greeting"
        return u
    if ACTION.search(low):
        u.reason = "action"                     # the copilot explains; it never changes or approves anything
        return u
    if HYPOTHETICAL.search(low):
        if u.weather_type or u.temp_max_c:
            u.intent = "whatif_weather"
        elif u.pct is not None:
            u.intent = "whatif_attendance"
        elif u.flags:
            u.intent = "whatif_special_day"
        else:
            u.reason = "unclear_change"   # a what if, but not one of the changes the dashboard can try
        return u
    planning = bool(PLAN_WORDS.search(low))
    if (planning or WHY_WORDS.search(low)) and not u.dish_ids:   # "how much rice", "why is paneer high"
        u.dish_ids = _partial_dishes(toks, dish_keys)
    if RANGE_WORDS.search(low) and not u.dish_ids:
        u.intent = "explain_range"
    elif RISK_WORDS.search(low):
        u.intent = "summarise_surplus_risk"
    elif u.dish_ids:
        u.intent = "explain_dish"
    elif WEEK_WORDS.search(low) or [e for e in ents if e.type == "WEEKDAY"]:
        u.intent = "explain_week"
    elif RANGE_WORDS.search(low):
        u.intent = "explain_range"
    elif WHY_WORDS.search(low) and ({"plan", "forecast", "demand", "portions", "cook", "cooking", "high", "low", "higher", "lower"} & set(toks)):
        u.intent = "explain_dish"               # about the whole slot against the usual plan
    elif planning:
        u.intent = "explain_dish"               # "what should we cook": the slot's plan against the usual plan
    else:
        u.reason = "off_topic"
    return u


def resolve_day(u: Understanding, fallback: Date, today: Date) -> Date:
    """The date a question is about: an ISO date, today, tomorrow, a weekday within the next 7 days, or the page's day."""
    for w in u.day_words:
        w = w.lower()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", w):
            return Date.fromisoformat(w)
        if w == "today":
            return today
        if w == "tomorrow":
            return today + timedelta(days=1)
        if w in WEEKDAYS:
            for i in range(1, 8):
                if (today + timedelta(days=i)).strftime("%A").lower() == w:
                    return today + timedelta(days=i)
    return fallback


def pos_hints(question: str) -> dict:
    """POS based candidates (nouns and numbers), kept for the report and for debugging."""
    return candidate_entities(question)
