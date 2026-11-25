"""TF-IDF vector index over document chunks (retrieval step of the RAG pipeline)."""
from __future__ import annotations

import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer

from .ingest import Chunk

_WORD_RE = re.compile(r"[a-z]+")
_SUFFIXES = ("ation", "ate", "ing", "ed", "es", "s", "e")


def _stem(word: str) -> str:
    """Very light suffix stripping so 'irrigate', 'irrigation' and 'irrigated' match."""
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> list[str]:
    return [_stem(w) for w in _WORD_RE.findall(text.lower()) if w not in ENGLISH_STOP_WORDS]


class Retriever:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self._vectorizer: TfidfVectorizer | None = None
        self._matrix = None

    def add(self, chunks: list[Chunk]) -> None:
        """Add chunks and rebuild the index once."""
        if not chunks:
            return
        self.chunks.extend(chunks)
        self._rebuild()

    def _rebuild(self) -> None:
        self._vectorizer = TfidfVectorizer(
            tokenizer=tokenize,
            token_pattern=None,
            lowercase=False,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self._matrix = self._vectorizer.fit_transform([c.text for c in self.chunks])

    def search(self, query: str, k: int = 4) -> list[tuple[Chunk, float]]:
        """Return up to k (chunk, cosine similarity) pairs with a score above zero, best first."""
        if self._vectorizer is None or not self.chunks:
            return []
        query_vec = self._vectorizer.transform([query])
        scores = (self._matrix @ query_vec.T).toarray().ravel()
        order = scores.argsort()[::-1][:k]
        return [(self.chunks[i], float(scores[i])) for i in order if scores[i] > 0]

    def sources(self) -> dict[str, int]:
        """Map of source file name to number of chunks indexed from it."""
        counts: dict[str, int] = {}
        for chunk in self.chunks:
            counts[chunk.source] = counts.get(chunk.source, 0) + 1
        return counts
