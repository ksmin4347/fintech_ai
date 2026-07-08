"""Embedding client with OpenAI optional and TF-IDF fallback."""

from __future__ import annotations

import os
from typing import Literal

RetrieverMode = Literal["tfidf", "openai"]


class EmbeddingClient:
    def __init__(self):
        self.use_openai = (
            os.getenv("USE_OPENAI", "false").lower() == "true"
            and bool(os.getenv("OPENAI_API_KEY"))
        )
        self.model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
        self._vectorizer = None
        self._matrix = None
        self._texts: list[str] = []

    def mode(self) -> RetrieverMode:
        return "openai" if self.use_openai else "tfidf"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self.use_openai:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                resp = client.embeddings.create(model=self.model, input=texts)
                return [d.embedding for d in resp.data]
            except Exception:
                self.use_openai = False
        return self._tfidf_embed(texts)

    def _tfidf_embed(self, texts: list[str]) -> list[list[float]]:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._texts = texts
        self._vectorizer = TfidfVectorizer(max_features=5000)
        self._matrix = self._vectorizer.fit_transform(texts)
        return self._matrix.toarray().tolist()

    def embed_query(self, query: str) -> list[float]:
        if self._vectorizer is not None and self._texts:
            vec = self._vectorizer.transform([query])
            return vec.toarray()[0].tolist()
        return self.embed_texts([query])[0]
