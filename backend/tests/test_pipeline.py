"""Unit tests: ingestion, retrieval, escalation and the RAG decision logic."""
import io
from dataclasses import replace

import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app import llm as llm_module
from app.config import settings
from app.ingest import build_chunks, chunk_text
from app.llm import LLMError, OpenAICompatibleLLM, build_llm
from app.rag import RAGService
from app.safety import assess


class FakeLLM:
    name = "fake"
    model = "fake-model"

    def __init__(self, reply="Remove affected lower leaves and apply a labelled fungicide [1]."):
        self.calls = 0
        self.reply = reply

    def complete(self, system, user):
        self.calls += 1
        assert "CONTEXT:" in user and "QUESTION:" in user
        return self.reply


class BrokenLLM:
    name = "broken"
    model = "x"

    def complete(self, system, user):
        raise LLMError("simulated outage")


def make_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 760, text)
    c.showPage()
    c.drawString(72, 760, "Second page: scout fields weekly.")
    c.save()
    return buf.getvalue()


# ---------- ingestion ----------

def test_chunk_text_overlaps_and_covers_all_words():
    text = " ".join(f"w{i}" for i in range(10))
    chunks = chunk_text(text, size=4, overlap=1)
    assert chunks[0] == "w0 w1 w2 w3"
    assert chunks[1].startswith("w3 ")
    assert chunks[-1].endswith("w9")


def test_chunk_text_rejects_bad_overlap():
    with pytest.raises(ValueError):
        chunk_text("a b c", size=3, overlap=3)


def test_pdf_ingestion_keeps_page_numbers_and_text():
    chunks = build_chunks("fall_armyworm.pdf", make_pdf("Fall armyworm larvae feed in the whorl."), 120, 20)
    assert chunks, "PDF produced no chunks"
    assert any("armyworm" in c.text for c in chunks)
    assert {c.page for c in chunks} == {1, 2}
    assert all(c.source == "fall_armyworm.pdf" for c in chunks)


def test_unsupported_file_type_is_rejected():
    with pytest.raises(ValueError):
        build_chunks("photo.jpg", b"\xff\xd8", 120, 20)


# ---------- retrieval ----------

def test_retrieval_finds_the_right_guide(retriever):
    hits = retriever.search("dark rings on the lower leaves of my tomato plants", k=4)
    assert hits and hits[0][0].source == "tomato_guide.txt"


def test_retrieval_handles_word_forms(retriever):
    # "irrigate" should match the wheat guide's "irrigation" wording.
    hits = retriever.search("when should I irrigate wheat", k=4)
    assert hits and hits[0][0].source == "wheat_guide.txt"


def test_unrelated_query_scores_below_threshold(retriever):
    hits = retriever.search("best recipe for chocolate cake", k=4)
    top = hits[0][1] if hits else 0.0
    assert top < settings.min_confidence


# ---------- escalation rules ----------

def test_risk_terms_escalate_even_with_strong_retrieval():
    decision = assess("my farmer drank pesticide by mistake", top_score=0.9, min_confidence=0.1)
    assert decision.escalate and decision.reason == "risk"


def test_low_confidence_escalates():
    decision = assess("capital of France", top_score=0.0, min_confidence=0.1)
    assert decision.escalate and decision.reason == "low_confidence"


def test_normal_question_is_answered():
    decision = assess("how to control early blight", top_score=0.25, min_confidence=0.1)
    assert not decision.escalate and decision.reason is None


# ---------- RAG service ----------

def test_risky_query_never_reaches_the_llm(retriever):
    llm = FakeLLM()
    rag = RAGService(retriever, llm, top_k=4, min_confidence=0.1)
    result = rag.answer("I think I got poisoned after I sprayed, what should I do?")
    assert result["escalated"] is True and result["reason"] == "risk"
    assert result["answer"] is None and result["citations"] == []
    assert llm.calls == 0


def test_low_confidence_query_never_reaches_the_llm(retriever):
    llm = FakeLLM()
    rag = RAGService(retriever, llm, top_k=4, min_confidence=0.1)
    result = rag.answer("best recipe for chocolate cake")
    assert result["escalated"] is True and result["reason"] == "low_confidence"
    assert llm.calls == 0


def test_generated_answer_has_citations(retriever):
    llm = FakeLLM()
    rag = RAGService(retriever, llm, top_k=4, min_confidence=0.1)
    result = rag.answer("How do I control early blight on tomato?")
    assert result["mode"] == "generative" and not result["escalated"]
    assert llm.calls == 1
    assert "[1]" in result["answer"]
    assert result["citations"][0]["source"] == "tomato_guide.txt"
    assert result["citations"][0]["page"] == 1


def test_llm_failure_falls_back_to_retrieved_passages(retriever):
    rag = RAGService(retriever, BrokenLLM(), top_k=4, min_confidence=0.1)
    result = rag.answer("How do I control early blight on tomato?")
    assert result["mode"] == "fallback"
    assert "unavailable" in result["warning"]
    assert result["citations"]


def test_retrieval_only_mode_without_llm(retriever):
    rag = RAGService(retriever, None, top_k=4, min_confidence=0.1)
    result = rag.answer("How much nitrogen for rice?")
    assert result["mode"] == "extractive"
    assert result["citations"] and "[1]" in result["answer"]


def test_empty_question_is_rejected(retriever):
    rag = RAGService(retriever, None, top_k=4, min_confidence=0.1)
    with pytest.raises(ValueError):
        rag.answer("   ")


# ---------- LLM client plumbing ----------

def test_build_llm_returns_none_without_key():
    assert build_llm(replace(settings, llm_provider="openai", llm_api_key="")) is None
    assert build_llm(replace(settings, llm_provider="none")) is None


def test_openai_client_parses_response(monkeypatch):
    class Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "  Use neem spray [1].  "}}]}

    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["url"], seen["auth"] = url, headers["Authorization"]
        return Resp()

    monkeypatch.setattr(llm_module.httpx, "post", fake_post)
    client = OpenAICompatibleLLM("KEY", "gpt-test", "https://example.com/v1/")
    assert client.complete("sys", "user") == "Use neem spray [1]."
    assert seen["url"] == "https://example.com/v1/chat/completions"
    assert seen["auth"] == "Bearer KEY"


def test_openai_client_reports_http_errors(monkeypatch):
    class Resp:
        status_code = 401

        def json(self):
            return {}

    monkeypatch.setattr(llm_module.httpx, "post", lambda *a, **k: Resp())
    with pytest.raises(LLMError, match="HTTP 401"):
        OpenAICompatibleLLM("bad", "m", "https://example.com/v1").complete("s", "u")
