"""Text pipeline: cleaning, tokens, stop words, matching, NER and preprocessing outputs."""

import pytest

from feedforward.data import nlp_text as T
from feedforward.data.loaders import load_table
from feedforward.data.nlp_entities import extract_entities, sense_of, split_sentences
from feedforward.data.preprocess import dish_catalogue, normalise_ids, process_weather


@pytest.fixture(scope="module")
def catalogue():
    return dish_catalogue(normalise_ids(load_table("dishes")))


def test_clean_and_display():
    assert T.clean_text("  Veg   Briyani!! ##") == "Veg Briyani"
    assert T.display_name(" tea ") == "Tea"
    assert T.display_name("Veg Briyani") == "Veg Briyani"  # case kept for display


def test_match_key_unifies_spelling():
    assert T.match_key("Veg Briyani") == T.match_key("veg biryani")
    assert T.match_key("Jeera Pulav") == T.match_key("jeera pulao")
    assert T.match_key("Spl. Chutney") == "special chutney"


def test_multi_word_expression_stays_single_entity():
    exprs = {("veg", "biryani"), ("light", "rain", "with", "thunder")}
    out = T.merge_expressions(["Veg", "Briyani", "and", "Light", "Rain", "with", "Thunder"], exprs)
    assert out == ["Veg_Briyani", "and", "Light_Rain_with_Thunder"]


def test_ngrams():
    assert T.ngrams(["a", "b", "c"], 2) == [("a", "b"), ("b", "c")]
    assert T.char_ngrams("ab", 2) == [" a", "ab", "b "]


def test_stopword_removal_keeps_negation():
    toks = ["No", "rain", "is", "expected"]
    assert "No" in T.remove_stopwords(toks)
    assert "No" not in T.remove_stopwords(toks, keep_negations=False)


def test_stemmer_makes_non_words_lemmatiser_does_not():
    assert T.stem_porter("gravy") == "gravi"
    assert T.lemmatize("fries") == "fry"


def test_fuzzy_match_and_review_list(catalogue):
    exact = T.fuzzy_match("  veg briyani ", catalogue)
    assert exact.match == "D090" and not exact.needs_review
    assert T.fuzzy_match("sambhar", catalogue).match == "D098"
    assert T.fuzzy_match("gobi sixty five", catalogue).needs_review
    assert T.fuzzy_match("zzzzqqq", catalogue).match is None


def test_raw_names_all_match_true_dish(catalogue):
    raw = load_table("kitchen_history_raw")[["dish_name", "dish_id"]].drop_duplicates()
    for name, dish_id in zip(raw["dish_name"], raw["dish_id"], strict=True):
        assert T.fuzzy_match(name, catalogue).match == dish_id


def test_sentence_split_keeps_abbreviation():
    assert split_sentences("Spl. Chutney is low. Why?") == ["Spl. Chutney is low.", "Why?"]


def test_ner_types(catalogue):
    ents = extract_entities("What if attendance rises 15% on Monday for veg briyani lunch "
                            "tomorrow during exam week with rain?", catalogue)
    types = {(e.type, e.value) for e in ents}
    assert ("PERCENT", 15.0) in types and ("WEEKDAY", "monday") in types
    assert ("DISH", "D090") in types and ("MEAL_SLOT", "lunch") in types
    assert ("EVENT", "exam_week") in types and ("WEATHER", "Rain") in types
    assert not any(e.type == "NUMBER" and e.value == 15.0 for e in ents)


def test_word_sense():
    assert sense_of("milk", "milk powder stock") == "ingredient"
    assert sense_of("sweet", "too sweet") == "adjective"
    assert sense_of("sweet", "the sweet for dinner") == "dish"


def test_weather_processing_flags():
    w = process_weather(load_table("weather"))
    assert "rainfall_mm_reported" not in w
    assert w.loc[w["data_quality"].str.startswith("UNVERIFIED"), "weather_reliable"].eq(0).all()
    assert w["temp_outlier"].sum() == 1
    assert w.loc[w["condition"].str.contains("Thunder"), "is_thunder"].eq(1).all()
