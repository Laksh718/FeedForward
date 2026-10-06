"""Feature extraction from text: bag of words, TF-IDF, cosine similarity, SVD embedding."""

import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from feedforward import config as C
from feedforward.data.nlp_text import match_key


class DishTextModel:
    """TF-IDF of dish names (word 1 to 2 grams plus character 2 to 4 grams) and a small embedding.

    The embedding (TF-IDF then SVD) is the hand engineered text feature. The VAE also learns its
    own dish embedding from data; comparing both is part of the report.
    """

    def __init__(self, dim: int = C.DISH_TEXT_DIM):
        self.dim = dim
        self.word = TfidfVectorizer(ngram_range=(1, 2))
        self.char = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))
        self.svd = TruncatedSVD(n_components=dim, random_state=C.SEED)
        self.ids: list[str] = []

    def fit(self, dishes: pd.DataFrame) -> "DishTextModel":
        """Fit on the dish catalogue (columns dish_id, dish_name)."""
        keys = [match_key(n) for n in dishes["dish_name"]]
        self.ids = dishes["dish_id"].tolist()
        self.matrix = hstack([self.word.fit_transform(keys), self.char.fit_transform(keys)]).tocsr()
        self.embedding = self.svd.fit_transform(self.matrix)
        return self

    def _vector(self, text: str):
        key = [match_key(text)]
        return hstack([self.word.transform(key), self.char.transform(key)]).tocsr()

    def most_similar(self, text: str, top: int = 3) -> list[tuple[str, float]]:
        """Cosine similarity of a typed name to every dish; returns (dish_id, score)."""
        sims = cosine_similarity(self._vector(text), self.matrix)[0]
        order = np.argsort(-sims)[:top]
        return [(self.ids[i], float(sims[i])) for i in order]

    def embedding_table(self) -> pd.DataFrame:
        """One row per dish: text_emb_0 .. text_emb_{dim-1}."""
        cols = [f"text_emb_{i}" for i in range(self.dim)]
        return pd.DataFrame(self.embedding, columns=cols).assign(dish_id=self.ids)


def bag_of_words(names: list[str]) -> pd.DataFrame:
    """Plain bag of words counts (shown in the report next to TF-IDF)."""
    cv = CountVectorizer()
    mat = cv.fit_transform([match_key(n) for n in names])
    return pd.DataFrame(mat.toarray(), columns=cv.get_feature_names_out())
