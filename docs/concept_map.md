# Concept map

Slide deck topics are named by subject. Rows marked (M3) or later are added when that code exists.

## NLP and text (built in M1 and M2)

| Concept | Slide deck topic | Where it is used | Why it fits |
|---|---|---|---|
| NLP project phases | NLP pipeline | `docs/pipeline.md` | Structures the whole project |
| Structured, semi, unstructured data | Data types | `docs/data_dictionary.md` | Every field is classified |
| Text cleaning | Text preprocessing | `nlp_text.clean_text` | Raw dish names have stray spaces and symbols |
| Lowercasing | Text preprocessing | `nlp_text.match_key` vs `display_name` | Matching ignores case, the screen keeps it |
| Tokenisation and multi word expressions | Tokenisation | `nlp_text.tokenize_*`, `merge_expressions` | "Veg Briyani" must stay one dish |
| n-grams (word and character) | Language models, n-grams | `text_features.DishTextModel` | Character n-grams survive spelling differences |
| Stop word removal (and its risk) | Text preprocessing | `nlp_text.remove_stopwords`, report section 2 | Only for intent detection; "no rain" must keep "no" |
| Stemming and lemmatisation | Morphology | `nlp_text.stem_*`, `lemmatize`, `reports/nlp_normalisation_report.md` | Compared on dish tokens, failures shown |
| Spelling correction, normalisation | Text normalisation | `nlp_text.SPELLING_MAP`, `fuzzy_match` | Maps raw and typed names to the catalogue (100 percent on the raw file) |
| POS tagging | Syntax | `nlp_entities.pos_tag`, `candidate_entities` | Finds nouns and numbers in copilot questions |
| Named entity recognition | Information extraction | `nlp_entities.extract_entities` | Finds dish, slot, day, weather, event, percent |
| Word sense disambiguation | Semantics | `nlp_entities.sense_of` | "milk" dish or ingredient, "sweet" dish or adjective |
| Sentence boundary detection | Text segmentation | `nlp_entities.split_sentences` | Does not split at "Spl." |
| Bag of words, TF-IDF, cosine similarity | Text representation | `text_features.py` | Dish similarity, dish text embedding |
| SVD embedding | Dimensionality reduction | `text_features.DishTextModel` | 8 numbers per dish, used as input features |
| NLU and NLG | Dialogue systems | `copilot/nlu.py` and `copilot/explain.py` (M6) | Rules understand, the LLM only writes the explanation |

## Deep learning and generative (M3 onward)

Neuron, activation, loss, backpropagation, Adam, overfitting controls, autoencoder, VAE, reparameterisation,
generative versus discriminative, reconstruction error anomaly check, GRU encoder and transformer use are
mapped here when the models are built.

## Not applicable, and why

- Machine translation: all text is English.
- CNN, VGG and image models: the data is tabular and time series, there are no images.
- Training a transformer: the hosted LLM is used only to write explanations, no training.
