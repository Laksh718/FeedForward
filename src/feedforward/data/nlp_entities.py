"""Sentence splitting, POS tagging, rule based NER and word sense rules for typed questions.

All rule and gazetteer based: no model is trained and no LLM is used here. This is the NLU
front end of the copilot (intent plus entities). Stop words are NOT removed before NER.
"""

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from feedforward.data.nlp_text import (
    clean_text,
    fuzzy_match,
    has,
    match_key,
    stop_words,
    tokenize_word,
)

MEAL_SLOTS = {"breakfast": "breakfast", "lunch": "lunch", "snacks": "snacks", "snack": "snacks",
              "dinner": "dinner", "supper": "dinner", "tiffin": "breakfast"}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
RELATIVE_DAYS = {"today": 0, "tomorrow": 1}
WEATHER_WORDS = {"rain": "Rain", "rainy": "Rain", "raining": "Rain", "rains": "Rain", "rained": "Rain", "downpour": "Rain",
                 "showers": "Drizzle", "drizzle": "Drizzle",
                 "thunder": "Thunder", "storm": "Thunder", "hot": "Hot", "heat": "Hot",
                 "fog": "Fog", "mist": "Mist", "haze": "Haze", "cloudy": "Partly Cloudy",
                 "dry": "Dry", "sunny": "Fair", "fair": "Fair"}
EVENT_PATTERNS = {
    "exam_week": r"\b(exam|exams|examination|formative test|theory exam|test week)\b",
    "festival": r"\b(festival|deepavali|diwali|pongal|ayudha puja|vijayadashami|christmas)\b",
    "holiday": r"\b(holiday|holidays|vacation|semester break)\b",
}
ABBREV = ["spl", "mr", "mrs", "dr", "vs", "no", "approx", "st"]


@dataclass(frozen=True)
class Entity:
    """One detected entity: type, original text span, normalised value."""

    type: str
    text: str
    value: str | float | None = None


def split_sentences(text: str) -> list[str]:
    """Sentence boundary detection that does not break at abbreviations like 'Spl.'."""
    protected = text
    for ab in ABBREV:
        protected = re.sub(rf"\b({ab})\.", r"\1<DOT>", protected, flags=re.I)
    parts = re.split(r"(?<=[.!?])\s+", protected.strip())
    return [p.replace("<DOT>", ".") for p in parts if p]


def pos_tag(text: str) -> list[tuple[str, str]]:
    """Part of speech tags (NLTK tagger, or a simple number / noun fallback)."""
    tokens = tokenize_word(clean_text(text))
    if has("averaged_perceptron_tagger_eng"):
        import nltk

        return nltk.pos_tag(tokens)
    return [(t, "CD" if re.fullmatch(r"\d+(\.\d+)?%?", t) else "NN") for t in tokens]


def candidate_entities(text: str) -> dict[str, list[str]]:
    """Use POS tags to list candidate dish words (nouns) and numbers (cardinals)."""
    tagged = pos_tag(text)
    return {"nouns": [w for w, t in tagged if t.startswith("NN")],
            "numbers": [w for w, t in tagged if t == "CD"]}


# ---------------------------------------------------------------- word sense rules
_INGREDIENT_CONTEXT = re.compile(r"\b(milk)\b\s+(powder|stock|litres?|liters?|kg|used|usage|"
                                 r"ingredient)|\b(ingredient|stock of)\s+milk")
_ADJ_SWEET = re.compile(r"\b(too|very|less|more|bit|so|extra)\s+sweet\b|\bsweet\s+(tooth|taste|"
                        r"potato|corn|lime)\b")


def sense_of(word: str, text: str) -> str:
    """Small word sense disambiguation: 'milk' and 'sweet' as a dish or something else."""
    low = text.lower()
    if word == "milk":
        return "ingredient" if _INGREDIENT_CONTEXT.search(low) else "dish"
    if word == "sweet":
        return "adjective" if _ADJ_SWEET.search(low) else "dish"
    return "dish"


# ---------------------------------------------------------------- NER
def _dish_entities(text: str, dish_keys: dict[str, str], max_len: int = 5) -> list[Entity]:
    """Gazetteer lookup of dish names over word windows, longest first, spelling tolerant."""
    words = match_key(text).split()
    stops = stop_words()  # only used to stop fuzzy windows starting or ending on a filler word
    found, i = [], 0
    while i < len(words):
        hit = None
        for n in range(min(max_len, len(words) - i), 0, -1):
            phrase = " ".join(words[i:i + n])
            if phrase in dish_keys:
                hit = (n, dish_keys[phrase], phrase)
            elif len(phrase) >= 5 and words[i] not in stops and words[i + n - 1] not in stops:
                res = fuzzy_match(phrase, dish_keys, threshold=88, review_floor=88,
                                  scorer=fuzz.ratio)
                if res.match and not res.needs_review:
                    hit = (n, res.match, phrase)
            if hit:
                break
        near = " ".join(words[max(0, i - 2):i + hit[0] + 2]) if hit else ""
        if hit and sense_of(hit[2], near) == "dish":
            found.append(Entity("DISH", hit[2], hit[1]))
            i += hit[0]
        else:
            i += hit[0] if hit else 1
    return found


def extract_entities(text: str, dish_keys: dict[str, str]) -> list[Entity]:
    """Rule and gazetteer NER: DISH, MEAL_SLOT, WEEKDAY, DATE, WEATHER, EVENT, PERCENT, NUMBER."""
    clean = clean_text(text)
    low = clean.lower()
    ents = _dish_entities(clean, dish_keys)
    words = re.findall(r"[a-z]+", low)
    ents += [Entity("MEAL_SLOT", w, MEAL_SLOTS[w]) for w in words if w in MEAL_SLOTS]
    ents += [Entity("WEEKDAY", w, w) for w in words if w in WEEKDAYS]
    ents += [Entity("DATE", w, RELATIVE_DAYS[w]) for w in words if w in RELATIVE_DAYS]
    ents += [Entity("DATE", m, m) for m in re.findall(r"\b\d{4}-\d{2}-\d{2}\b", low)]
    ents += [Entity("WEATHER", w, WEATHER_WORDS[w]) for w in words if w in WEATHER_WORDS]
    for name, pattern in EVENT_PATTERNS.items():
        m = re.search(pattern, low)
        if m:
            ents.append(Entity("EVENT", m.group(0), name))
    pct = re.findall(r"(-?\d+(?:\.\d+)?)\s*(?:%|percent|per cent)", low)
    ents += [Entity("PERCENT", p, float(p)) for p in pct]
    pct_set = set(pct)
    nums = re.findall(r"(?<![\d-])(-?\d+(?:\.\d+)?)(?!\d|-\d|\s*(?:%|percent|per cent))", low)
    ents += [Entity("NUMBER", n, float(n)) for n in nums if n not in pct_set]
    return ents
