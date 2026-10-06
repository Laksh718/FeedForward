# Concept map

Slide deck topics are named by subject.

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

## Deep learning and generative (M3)

| Concept | Slide deck topic | Where it is used | Why it fits |
|---|---|---|---|
| Hand engineered features versus learned representations | Feature engineering, representation learning | `data/features.py` (hand made) and `CVAE.dish_emb` (learned) | Calendar, weather and lags are designed by us; the 8 numbers per dish are learned from data. The TF-IDF dish embedding is the hand made counterpart |
| Neuron, weights, bias, activation (ReLU, LeakyReLU, sigmoid) | Neural network basics | `models/cvae.py` (`nn.Linear`, `nn.LeakyReLU`) | LeakyReLU keeps a small slope for negative inputs so units never go fully dead. ReLU is the common default because it is cheap and avoids vanishing gradients |
| Forward propagation, loss, backpropagation, gradient descent, Adam, learning rate, epochs, batches | Training neural networks | `models/cvae.py: train_cvae` (comments mark each step) | The loop is written out explicitly so every team member can read it |
| Loss functions: MSE, MAE, RMSE, KL divergence | Loss functions | `cvae.vae_loss`, `models/metrics.py` | Gaussian negative log likelihood generalises MSE (it also learns the variance); KL pulls the encoder toward the prior; MAE and RMSE judge forecasts in portions |
| Overfitting, underfitting, early stopping, dropout, weight decay | Regularisation | `train_cvae` (early stopping), `CVAEConfig` (dropout 0.1, weight decay), `reports/learning_curves.png` | Validation loss turns upward after about 30 epochs, so the best epoch is kept |
| Autoencoder: encoder, latent space, decoder, undercomplete design | Autoencoders | `CVAE` (latent size 8 versus 70 plus inputs) | A small bottleneck forces a compact summary |
| VAE: mean and log variance, reparameterisation trick, Gaussian prior, sampling | Variational autoencoders | `CVAE.forward`, `sample_log_quantiles` | Sampling z from N(0, I) and decoding gives many plausible demands, which are turned into P10, P50, P90 |
| Posterior collapse, KL annealing, free bits | VAE training tricks | `beta_at`, `vae_loss(free_bits)`, collapse table in `reports/metrics_summary.md` | We measured KL per latent dimension. Without free bits the latent space was unused |
| Generative versus discriminative | Generative models | `models/cvae.py` (models p(demand given conditions)) against `GBMQuantile` (predicts quantiles directly) | Both give ranges, and the report compares them honestly |
| Reconstruction error as an anomaly signal | Autoencoder anomaly detection | `admin/validation.py` (M7) | Entered values far outside the forecast range raise a typo warning |
| Sequence models: RNN, LSTM, GRU and gates | Recurrent networks | `data/timeseries.py` (21 day windows), `CVAEConfig(encoder="gru")`, `train --encoder gru` | Optional experiment. A GRU summarises the history; its update and reset gates decide what to keep or forget. Result: no gain over the MLP (see metrics_summary.md) |
| Transformers and LLMs, attention | Transformers | `copilot/llm.py` (M6), `docs/` | The hosted LLM is only used to write explanations; attention lets it weigh which words in the question and the figures matter. No training |

## Not applicable, and why

- Machine translation: all text is English.
- CNN, VGG and image models: the data is tabular and time series, there are no images.
- Training a transformer: the hosted LLM is used only to write explanations, no training.
