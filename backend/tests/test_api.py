"""API tests for the RAG endpoints (uses the real startup loader and the test database)."""
import io

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


def make_pdf(text: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.drawString(72, 760, text)
    c.save()
    return buf.getvalue()


def test_health_reports_models_and_documents(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["documents"] >= 5 and body["chunks"] > 0
    assert body["llm_configured"] is False
    assert body["disease_model_loaded"] is True
    assert body["crop_model_loaded"] is True


def test_ask_requires_login(client):
    r = client.post("/api/ask", json={"question": "How do I manage early blight?"})
    assert r.status_code == 401


def test_ask_returns_answer_with_citations(client, auth_headers):
    r = client.post("/api/ask", json={"question": "How do I manage early blight on tomato leaves?"}, headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["escalated"] is False
    assert body["citations"][0]["source"] == "tomato_guide.txt"
    assert body["citations"][0]["page"] == 1


def test_ask_escalates_risky_question(client, auth_headers):
    body = client.post("/api/ask", json={"question": "my son swallowed pesticide, what now"}, headers=auth_headers).json()
    assert body["escalated"] is True and body["reason"] == "risk"
    assert "112" in body["message"]


def test_ask_rejects_too_short_question(client, auth_headers):
    assert client.post("/api/ask", json={"question": "hi"}, headers=auth_headers).status_code == 422


def test_upload_pdf_is_indexed_and_duplicate_rejected(client, auth_headers):
    pdf = make_pdf("Mango hopper control: spray only when the threshold is crossed.")
    r = client.post("/api/documents", files={"file": ("mango_pests.pdf", pdf, "application/pdf")}, headers=auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["chunks"] >= 1
    again = client.post("/api/documents", files={"file": ("mango_pests.pdf", pdf, "application/pdf")}, headers=auth_headers)
    assert again.status_code == 409
    body = client.post("/api/ask", json={"question": "when to spray for mango hopper"}, headers=auth_headers).json()
    assert body["citations"][0]["source"] == "mango_pests.pdf"


def test_upload_rejects_unsupported_type(client, auth_headers):
    r = client.post("/api/documents", files={"file": ("photo.jpg", b"\xff\xd8\xff", "image/jpeg")}, headers=auth_headers)
    assert r.status_code == 400


def test_upload_rejects_pdf_without_text(client, auth_headers):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.showPage()
    c.save()
    r = client.post("/api/documents", files={"file": ("blank.pdf", buf.getvalue(), "application/pdf")}, headers=auth_headers)
    assert r.status_code == 422
