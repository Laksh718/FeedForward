"""Builds reports/nlp_normalisation_report.md: evidence for the text pipeline choices."""

import pandas as pd

from feedforward import config as C
from feedforward.data import nlp_text as T
from feedforward.data.loaders import load_table
from feedforward.data.nlp_entities import (
    candidate_entities,
    extract_entities,
    sense_of,
    split_sentences,
)
from feedforward.data.preprocess import dish_catalogue, normalise_ids
from feedforward.data.text_features import DishTextModel, bag_of_words

TOKEN_EXAMPLES = ["Veg Briyani", "Light Rain with Thunder", "Gobi 65", "Spl. Chutney, Idly Podi"]
STEM_WORDS = ["pulao", "pulav", "briyani", "biryani", "chappathi", "chapati", "masala", "fries",
              "poriyal", "chutney", "kuruma", "omelet", "gravy", "upma", "dosa", "idly", "vadai"]
TYPED_NAMES = ["veg biriyani", "chiken biryani", "paneer briyani", "jeera pulao", "chapati",
               "curd rice", "sambhar", "tomato pulav", "bread omlet", "gobi sixty five"]
QUESTIONS = ["Why is veg briyani below the usual plan for lunch tomorrow?",
             "What if attendance rises 15% on Monday during exam week?",
             "Will rain change the milk quantity? The sweet dish is too sweet. Spl. Chutney is low.",
             "No rain expected, how many portions of curd rice for dinner?"]


def _md_table(df: pd.DataFrame) -> str:
    """Render a DataFrame as a markdown table."""
    head = "| " + " | ".join(map(str, df.columns)) + " |\n|" + "---|" * len(df.columns) + "\n"
    rows = "".join("| " + " | ".join(map(str, r)) + " |\n" for r in df.itertuples(index=False))
    return head + rows


def tokeniser_section(expressions: set) -> str:
    """Compare whitespace, regex, word tokenisers and MWE merging."""
    rows = []
    for ex in TOKEN_EXAMPLES:
        merged = T.merge_expressions(T.tokenize_word(ex), expressions)
        rows.append({"text": ex, "whitespace": T.tokenize_whitespace(ex),
                     "regex": T.tokenize_regex(ex), "word": T.tokenize_word(ex), "with MWE": merged})
    return ("## 1. Tokenisers\nWhitespace keeps punctuation glued on, the regex drops it, the word "
            "tokeniser splits it off. Multi word expressions are then merged so a dish or weather "
            "phrase stays one entity.\n\n" + _md_table(pd.DataFrame(rows)))


def stopword_section() -> str:
    """Show why stop word removal is unsafe for negations."""
    sentence = "No rain is expected and the kitchen is not short of rice"
    toks = T.tokenize_word(sentence)
    return ("## 2. Stop words and negation\nRemoving every stop word turns a negative into the "
            "opposite meaning, so stop words are removed only for intent detection and negations "
            "are kept. Entity extraction never removes them.\n\n"
            f"- Original: `{sentence}`\n"
            f"- All stop words removed: `{T.remove_stopwords(toks, keep_negations=False)}`\n"
            f"- Negations kept (used by the copilot): `{T.remove_stopwords(toks)}`\n")


def stemming_section() -> str:
    """Compare Porter, regexp stemmer and WordNet lemmatiser on dish tokens."""
    rows = [{"word": w, "porter": T.stem_porter(w), "regexp": T.stem_regexp(w),
             "lemma": T.lemmatize(w), "match_key": T.match_key(w)} for w in STEM_WORDS]
    return ("## 3. Stemming versus lemmatisation\nStemmers chop suffixes and can create non words "
            "(`fries` becomes `fri`, `gravy` becomes `gravi`, `poriyal` becomes `poriy`). The "
            "lemmatiser only fixes real English plurals (`fries` becomes `fry`). "
            "Neither joins spelling variants such as briyani and "
            "biryani, or pulao and pulav, so a small documented map (`SPELLING_MAP`) is applied "
            "for matching. The last column shows the result.\n\n" + _md_table(pd.DataFrame(rows)))


def matching_section(catalogue: dict[str, str], dishes: pd.DataFrame) -> str:
    """Fuzzy match raw names to the catalogue and check against the true dish_id."""
    raw = load_table("kitchen_history_raw")
    pairs = raw[["dish_name", "dish_id"]].drop_duplicates()
    pairs["dish_id"] = pairs["dish_id"].str.strip().str.upper()
    res = pairs["dish_name"].map(lambda n: T.fuzzy_match(n, catalogue))
    pairs["predicted"] = [r.match for r in res]
    pairs["review"] = [r.needs_review for r in res]
    messy = pairs[pairs["dish_name"] != pairs["dish_name"].str.strip().str.title()]
    correct = (pairs["predicted"] == pairs["dish_id"]).mean() * 100
    typed = pd.DataFrame([{"typed": q, "match": (m := T.fuzzy_match(q, catalogue)).match,
                           "dish": dishes.set_index("dish_id")["dish_name"].get(m.match, "-"),
                           "score": round(m.score, 1), "review": m.needs_review}
                          for q in TYPED_NAMES])
    return (f"## 4. Fuzzy matching (rapidfuzz)\n- Distinct raw names: {len(pairs)}; messy "
            f"(case or padding): {len(messy)}\n- Matched to the true dish_id: {correct:.1f} percent\n"
            f"- Accepted at score >= {C.FUZZY_ACCEPT}, listed for review between "
            f"{C.FUZZY_REVIEW} and {C.FUZZY_ACCEPT}.\n\nTyped, misspelt names:\n\n" + _md_table(typed))


def features_section(dishes: pd.DataFrame, model: DishTextModel) -> str:
    """Show bag of words, TF-IDF similarity and the embedding size."""
    bow = bag_of_words(dishes["dish_name"].tolist())
    sims = pd.DataFrame([{"query": q, "closest": ", ".join(
        f"{dishes.set_index('dish_id')['dish_name'][i]} ({s:.2f})"
        for i, s in model.most_similar(q))} for q in ["veg biriyani", "ghee pongal", "tomato rasam"]])
    return (f"## 5. Text features\n- Bag of words: {bow.shape[1]} distinct words over "
            f"{bow.shape[0]} dishes.\n- TF-IDF: word 1 to 2 grams plus character 2 to 4 grams, "
            f"then SVD to {model.dim} dimensions (`text_emb_*` columns).\n\n" + _md_table(sims))


def entities_section(catalogue: dict[str, str]) -> str:
    """Show sentence splitting, POS candidates, NER and word sense rules."""
    parts = ["## 6. Sentences, POS, NER and word senses\n"]
    for q in QUESTIONS:
        ents = [f"{e.type}:{e.text}" for e in extract_entities(q, catalogue)]
        parts.append(f"- `{q}`\n  - sentences: {split_sentences(q)}\n  - candidates: "
                     f"{candidate_entities(q)}\n  - entities: {ents}")
    parts.append(f"\nWord sense rules: 'milk' in 'milk powder stock' is {sense_of('milk', 'milk powder stock')}, "
                 f"in 'how much milk' is {sense_of('milk', 'how much milk')}; 'sweet' in 'too sweet' is "
                 f"{sense_of('sweet', 'too sweet')}, in 'the sweet for dinner' is "
                 f"{sense_of('sweet', 'the sweet for dinner')}.")
    return "\n".join(parts) + "\n"


def main() -> None:
    """Write the report."""
    T.setup_nltk()
    dishes = normalise_ids(load_table("dishes"))
    catalogue = dish_catalogue(dishes)
    model = DishTextModel().fit(dishes)
    expressions = {tuple(k.split()) for k in catalogue if " " in k}
    expressions |= {("light", "rain", "with", "thunder"), ("showers", "in", "the", "vicinity")}
    body = "\n".join([
        "# NLP normalisation report\nGenerated by `python -m feedforward.data.nlp_report`. "
        f"NLTK resources available: {T.setup_nltk(download=False)}\n",
        tokeniser_section(expressions), stopword_section(), stemming_section(),
        matching_section(catalogue, dishes), features_section(dishes, model),
        entities_section(catalogue)])
    C.REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (C.REPORTS_DIR / "nlp_normalisation_report.md").write_text(body, encoding="utf-8")
    print("wrote reports/nlp_normalisation_report.md")


if __name__ == "__main__":
    main()
