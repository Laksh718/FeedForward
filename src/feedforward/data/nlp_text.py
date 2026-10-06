"""Text pipeline for dish names, weather text, event names and typed input.

NLP phases covered here: preprocessing (clean, lowercase, tokenise, normalise) and
fuzzy matching. Every NLTK resource is optional: if it cannot be loaded (offline), a simple
regex based fallback is used so the project still runs.
"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz, process

from feedforward import config as C

# ---------------------------------------------------------------- NLTK with offline fallback
_RESOURCES = {
    "punkt_tab": "tokenizers/punkt_tab",
    "wordnet": "corpora/wordnet",
    "averaged_perceptron_tagger_eng": "taggers/averaged_perceptron_tagger_eng",
    "stopwords": "corpora/stopwords",
}
_available: dict[str, bool] = {}


def setup_nltk(download: bool = True) -> dict[str, bool]:
    """Make NLTK resources available from artifacts/nltk_data. Never raises when offline."""
    if _available and not download:
        return _available
    try:
        import nltk
    except ImportError:
        return {name: False for name in _RESOURCES}
    C.NLTK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    if str(C.NLTK_DATA_DIR) not in nltk.data.path:
        nltk.data.path.insert(0, str(C.NLTK_DATA_DIR))
    for name, path in _RESOURCES.items():
        try:
            nltk.data.find(path)
            _available[name] = True
        except LookupError:
            ok = False
            if download:
                try:
                    ok = bool(nltk.download(name, download_dir=str(C.NLTK_DATA_DIR), quiet=True))
                except Exception:  # offline or blocked network
                    ok = False
            _available[name] = ok
    return _available


def has(resource: str) -> bool:
    """True when an NLTK resource can be used."""
    if not _available:
        setup_nltk()
    return _available.get(resource, False)


# ---------------------------------------------------------------- cleaning and normalising
# Spelling variants that neither stemmers nor lemmatisers can fix. Used for MATCHING only.
SPELLING_MAP = {
    "briyani": "biryani", "briyaani": "biryani", "pulav": "pulao", "pulaav": "pulao",
    "chappathi": "chapati", "chapathi": "chapati", "chappati": "chapati",
    "kuruma": "korma", "kurma": "korma", "raitha": "raita", "sabji": "sabzi",
    "idli": "idly", "omelette": "omelet", "vadai": "vada", "mattar": "matar", "daal": "dal",
    "kichadi": "khichdi", "kichdi": "khichdi", "poori": "puri", "tiffen": "tiffin",
    "chilly": "chilli", "veggie": "veg", "vegetable": "veg",
}
ABBREVIATIONS = {"spl": "special", "veg": "veg", "pnr": "paneer"}

_QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"',
                         "–": "-", "—": "-", " ": " "})
_STRAY = re.compile(r"[^\w\s'%/&.\-+]")  # keep letters, digits, and a few useful marks


def clean_text(text: object) -> str:
    """Remove stray symbols, standardise punctuation and collapse spaces. Keeps case."""
    if text is None or (isinstance(text, float) and text != text):
        return ""
    s = unicodedata.normalize("NFKC", str(text)).translate(_QUOTES)
    s = _STRAY.sub(" ", s)
    s = re.sub(r"\s*([.,;:!?])\s*(?=\s|$)", r"\1", s)  # no space before end punctuation
    return re.sub(r"\s+", " ", s).strip()


def display_name(text: object) -> str:
    """Name for the screen: cleaned, original case kept; all lower case input is title cased."""
    s = clean_text(text)
    return s.title() if s and s == s.lower() else s


def match_key(text: object) -> str:
    """Lower case key for matching: cleaned, abbreviations expanded, spelling variants unified."""
    words = re.findall(r"[a-z0-9]+(?:'[a-z]+)?", clean_text(text).lower())
    words = [ABBREVIATIONS.get(w, w) for w in words]
    return " ".join(SPELLING_MAP.get(w, w) for w in words)


# ---------------------------------------------------------------- tokenisation
def tokenize_whitespace(text: str) -> list[str]:
    """Split on spaces only. Keeps punctuation glued to words."""
    return text.split()


def tokenize_regex(text: str) -> list[str]:
    """Word characters only. Drops punctuation but splits 'Gobi 65' and 'Chef's' badly."""
    return re.findall(r"\w+", text)


def tokenize_word(text: str) -> list[str]:
    """NLTK word tokeniser (falls back to a regex that keeps punctuation as tokens)."""
    if has("punkt_tab"):
        from nltk.tokenize import word_tokenize

        return word_tokenize(text)
    return re.findall(r"\w+(?:'\w+)?|[^\w\s]", text)


def merge_expressions(tokens: list[str], expressions: set[tuple[str, ...]]) -> list[str]:
    """Multi word expression handling: join known phrases into one token with underscores.

    Expressions are given as match keys, so 'Veg Briyani' matches ('veg', 'biryani').
    Longest phrase wins, so a dish stays one entity and not two words.
    """
    longest = max((len(e) for e in expressions), default=1)
    lowered = [SPELLING_MAP.get(t.lower(), t.lower()) for t in tokens]
    out, i = [], 0
    while i < len(tokens):
        for n in range(min(longest, len(tokens) - i), 1, -1):
            if tuple(lowered[i:i + n]) in expressions:
                out.append("_".join(tokens[i:i + n]))
                i += n
                break
        else:
            out.append(tokens[i])
            i += 1
    return out


def ngrams(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    """Word n-grams: n=1 unigram, 2 bigram, 3 trigram."""
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def char_ngrams(text: str, n: int = 3) -> list[str]:
    """Character n-grams (with edge padding), robust to small spelling differences."""
    padded = f" {text} "
    return [padded[i:i + n] for i in range(len(padded) - n + 1)]


# ---------------------------------------------------------------- stop words
_FALLBACK_STOP = {"a", "an", "the", "is", "are", "was", "of", "to", "in", "on", "at", "for", "and",
                  "or", "why", "what", "how", "do", "does", "it", "this", "that", "be", "if",
                  "no", "not", "nor", "than", "too", "very"}
NEGATIONS = {"no", "not", "nor", "never", "don't", "doesn't", "isn't", "won't", "without"}


def stop_words() -> set[str]:
    """English stop words (NLTK list, or a small fallback list)."""
    if has("stopwords"):
        from nltk.corpus import stopwords

        return set(stopwords.words("english"))
    return set(_FALLBACK_STOP)


def remove_stopwords(tokens: list[str], keep_negations: bool = True) -> list[str]:
    """Drop stop words. Use ONLY for intent detection; keep them for entity extraction.

    Negations are kept by default because "no rain" must not become "rain".
    """
    stops = stop_words() - (NEGATIONS if keep_negations else set())
    return [t for t in tokens if t.lower() not in stops]


# ---------------------------------------------------------------- stemming and lemmatising
def stem_porter(word: str) -> str:
    """Porter stemmer: chops suffixes by rules, can produce non words."""
    from nltk.stem import PorterStemmer

    return PorterStemmer().stem(word)


def stem_regexp(word: str) -> str:
    """Regexp stemmer: strips a few simple suffixes."""
    from nltk.stem import RegexpStemmer

    return RegexpStemmer("ing$|s$|es$|ed$", min=4).stem(word)


def lemmatize(word: str) -> str:
    """WordNet lemmatiser (dictionary based). Falls back to stripping a plural s."""
    if has("wordnet"):
        from nltk.stem import WordNetLemmatizer

        try:
            return WordNetLemmatizer().lemmatize(word.lower())
        except LookupError:
            pass
    w = word.lower()
    return w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w


# ---------------------------------------------------------------- fuzzy matching
@dataclass(frozen=True)
class FuzzyResult:
    """Best catalogue match for a messy name."""

    query: str
    match: str | None
    score: float
    needs_review: bool


def fuzzy_match(query: str, catalogue: dict[str, str], threshold: float = C.FUZZY_ACCEPT,
                review_floor: float = C.FUZZY_REVIEW, scorer=fuzz.WRatio) -> FuzzyResult:
    """Match a messy name to the catalogue (match_key -> id) using rapidfuzz.

    score >= threshold: accepted. review_floor <= score < threshold: accepted but listed for
    human review. Below review_floor: no match.
    """
    key = match_key(query)
    if key in catalogue:
        return FuzzyResult(query, catalogue[key], 100.0, False)
    best = process.extractOne(key, list(catalogue), scorer=scorer)
    if best is None or best[1] < review_floor:
        return FuzzyResult(query, None, best[1] if best else 0.0, True)
    return FuzzyResult(query, catalogue[best[0]], float(best[1]), best[1] < threshold)
