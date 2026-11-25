"""RAG pipeline: retrieve -> decide (escalate or answer) -> generate with citations."""
from __future__ import annotations

from .ingest import Chunk
from .llm import BaseLLM, LLMError
from .retriever import Retriever
from .safety import ESCALATION_MESSAGES, assess

SYSTEM_PROMPT = (
    "You are AgriAssist, an advisory assistant for farmers. "
    "Answer ONLY from the numbered CONTEXT passages. After each claim, cite the passage number in "
    "square brackets, for example [1] or [2]. If the context does not contain the answer, say so "
    "and advise the farmer to contact a local agriculture officer. Do not invent doses, dates or "
    "chemical names that are not in the context. Keep the answer short, practical and in plain "
    "language. Reply in the same language as the QUESTION."
)


def _snippet(text: str, words: int = 40) -> str:
    parts = text.split()
    return " ".join(parts[:words]) + ("..." if len(parts) > words else "")


def _citation(number: int, chunk: Chunk, score: float) -> dict:
    return {
        "id": number,
        "source": chunk.source,
        "page": chunk.page,
        "score": round(score, 3),
        "snippet": _snippet(chunk.text),
    }


def _format_context(hits: list[tuple[Chunk, float]]) -> str:
    return "\n\n".join(
        f"[{i}] (source: {c.source}, page {c.page})\n{c.text}" for i, (c, _) in enumerate(hits, start=1)
    )


class RAGService:
    def __init__(self, retriever: Retriever, llm: BaseLLM | None, top_k: int, min_confidence: float) -> None:
        self.retriever = retriever
        self.llm = llm
        self.top_k = top_k
        self.min_confidence = min_confidence

    def answer(self, question: str) -> dict:
        question = " ".join(question.split())
        if not question:
            raise ValueError("The question is empty.")

        hits = self.retriever.search(question, self.top_k)
        top_score = hits[0][1] if hits else 0.0
        decision = assess(question, top_score, self.min_confidence)
        # Weak secondary matches would only mislead the model and the reader, so drop them.
        hits = [(c, s) for c, s in hits if s >= self.min_confidence]

        if decision.escalate:
            # Risky and low-confidence questions never reach the language model.
            return {
                "mode": "escalated",
                "escalated": True,
                "reason": decision.reason,
                "message": ESCALATION_MESSAGES[decision.reason],
                "answer": None,
                "confidence": round(top_score, 3),
                "citations": [],
                "warning": None,
            }

        if self.llm is None:
            return self._retrieval_only(hits, top_score, mode="extractive", warning=None)

        try:
            answer = self.llm.complete(
                SYSTEM_PROMPT,
                f"CONTEXT:\n{_format_context(hits)}\n\nQUESTION: {question}",
            )
        except LLMError as exc:
            return self._retrieval_only(
                hits, top_score, mode="fallback",
                warning=f"The AI model is unavailable, so the most relevant passages are shown instead. ({exc})",
            )

        return {
            "mode": "generative",
            "escalated": False,
            "reason": None,
            "message": None,
            "answer": answer,
            "confidence": round(top_score, 3),
            "citations": [_citation(i, c, s) for i, (c, s) in enumerate(hits, start=1)],
            "warning": None,
        }

    def _retrieval_only(self, hits, top_score: float, mode: str, warning: str | None) -> dict:
        parts = [f"{_snippet(c.text, 60)} [{i}]" for i, (c, _) in enumerate(hits[:2], start=1)]
        return {
            "mode": mode,
            "escalated": False,
            "reason": None,
            "message": None,
            "answer": "\n\n".join(parts),
            "confidence": round(top_score, 3),
            "citations": [_citation(i, c, s) for i, (c, s) in enumerate(hits, start=1)],
            "warning": warning,
        }
