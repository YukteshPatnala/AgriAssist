"""FastAPI application: REST API for the AgriAssist Smart Agriculture Platform."""
from __future__ import annotations

import io
import json
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .auth import current_user, hash_password, make_token, verify_password
from .config import DB_PATH, DOCS_DIR, MODELS_DIR, UPLOADS_DIR, settings
from .db import Database
from .ingest import SUPPORTED_SUFFIXES, build_chunks
from .llm import build_llm, check_connection
from .ml.classifier import get_disease_classifier
from .ml.crop import get_crop_recommender
from .rag import RAGService
from .retriever import Retriever
from .services import finance, soil, weather
from .services.market import MarketError, fetch_prices, summarize

LANGUAGES = {"en", "hi", "kn"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DISEASE_DISCLAIMER = (
    "This is a machine-learning estimate from one photo, trained on PlantVillage lab images. "
    "It is not a diagnosis. Confirm with a local agriculture officer before treating the crop."
)


def _load_folder(folder: Path) -> list:
    chunks = []
    if not folder.exists():
        return chunks
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() in SUPPORTED_SUFFIXES and path.is_file():
            chunks.extend(build_chunks(path.name, path.read_bytes(), settings.chunk_words, settings.chunk_overlap))
    return chunks


@asynccontextmanager
async def lifespan(app: FastAPI):
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.state.db = Database(DB_PATH)
    retriever = Retriever()
    retriever.add(_load_folder(DOCS_DIR) + _load_folder(UPLOADS_DIR))
    llm = build_llm(settings)
    app.state.retriever = retriever
    app.state.llm = llm
    app.state.rag = RAGService(retriever, llm, settings.top_k, settings.min_confidence)
    yield


app = FastAPI(title="AgriAssist Smart Agriculture API", version="2.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- request models
class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    password: str = Field(min_length=8, max_length=128)
    language: str = "en"


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1, max_length=128)


class LanguageUpdate(BaseModel):
    language: str


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class CropRequest(BaseModel):
    N: float = Field(ge=0, le=300)
    P: float = Field(ge=0, le=300)
    K: float = Field(ge=0, le=300)
    temperature: float = Field(ge=-10, le=55)
    humidity: float = Field(ge=0, le=100)
    ph: float = Field(ge=0, le=14)
    rainfall: float = Field(ge=0, le=3000)


class SoilRequest(BaseModel):
    nitrogen: float = Field(ge=0, le=2000)
    phosphorus: float = Field(ge=0, le=500)
    potassium: float = Field(ge=0, le=2000)
    ph: float = Field(ge=0, le=14)
    organic_carbon: float = Field(ge=0, le=10)


class FinanceRequest(BaseModel):
    area_acres: float = Field(gt=0, le=100000)
    yield_per_acre: float = Field(ge=0, le=1000)
    price_per_quintal: float = Field(ge=0, le=100000)
    seed_cost: float = Field(default=0, ge=0)
    fertilizer_cost: float = Field(default=0, ge=0)
    pesticide_cost: float = Field(default=0, ge=0)
    labour_cost: float = Field(default=0, ge=0)
    irrigation_cost: float = Field(default=0, ge=0)
    other_cost: float = Field(default=0, ge=0)
    lease_per_acre: float = Field(default=0, ge=0)
    loan_amount: float = Field(default=0, ge=0)
    loan_rate_pct: float = Field(default=0, ge=0, le=36)
    loan_years: int = Field(default=0, ge=0, le=30)


class WatchRequest(BaseModel):
    commodity: str = Field(min_length=2, max_length=60)
    threshold: float = Field(gt=0, le=1000000)


def _public_user(user: dict) -> dict:
    return {"id": user["id"], "name": user["name"], "email": user["email"], "language": user["language"]}


def _notify(db: Database, user_id: int, kind: str, title: str, body: str) -> bool:
    """Create an unread notification unless an identical unread one already exists."""
    if db.one("SELECT id FROM notifications WHERE user_id=? AND kind=? AND body=? AND read=0", (user_id, kind, body)):
        return False
    db.execute(
        "INSERT INTO notifications (user_id, kind, title, body, read, created_at) VALUES (?, ?, ?, ?, 0, ?)",
        (user_id, kind, title, body, datetime.now(timezone.utc).isoformat()),
    )
    return True


# ---------------------------------------------------------------- health and models
@app.get("/api/health")
def health(request: Request):
    state = request.app.state
    return {
        "status": "ok",
        "llm_configured": state.llm is not None,
        "llm_provider": state.llm.name if state.llm else "none",
        "documents": len(state.retriever.sources()),
        "chunks": len(state.retriever.chunks),
        "disease_model_loaded": get_disease_classifier() is not None,
        "crop_model_loaded": get_crop_recommender() is not None,
        "market_key_configured": bool(settings.datagov_api_key),
    }


@app.get("/api/models")
def model_metrics():
    """Measured metrics of the trained models, shown on the dashboard."""
    result = {}
    for name in ("disease_metrics", "crop_metrics"):
        path = MODELS_DIR / f"{name}.json"
        if path.exists():
            result[name] = json.loads(path.read_text(encoding="utf-8"))
    return result


# ---------------------------------------------------------------- auth
@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterRequest, request: Request):
    db: Database = request.app.state.db
    email = payload.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if payload.language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported language.")
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    user_id = db.execute(
        "INSERT INTO users (name, email, password_hash, language, created_at) VALUES (?, ?, ?, ?, ?)",
        (payload.name.strip(), email, hash_password(payload.password), payload.language,
         datetime.now(timezone.utc).isoformat()),
    )
    user = db.one("SELECT id, name, email, language FROM users WHERE id=?", (user_id,))
    _notify(db, user_id, "welcome", "Welcome to AgriAssist",
            "Ask a question, check the weather, or analyse your soil to get started.")
    return {"token": make_token(user_id, settings.auth_secret, settings.token_hours), "user": _public_user(user)}


@app.post("/api/auth/login")
def login(payload: LoginRequest, request: Request):
    db: Database = request.app.state.db
    user = db.one("SELECT * FROM users WHERE email=?", (payload.email.strip().lower(),))
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")
    return {"token": make_token(user["id"], settings.auth_secret, settings.token_hours), "user": _public_user(user)}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return user


@app.patch("/api/me")
def update_me(payload: LanguageUpdate, request: Request, user: dict = Depends(current_user)):
    if payload.language not in LANGUAGES:
        raise HTTPException(status_code=400, detail="Unsupported language.")
    request.app.state.db.execute("UPDATE users SET language=? WHERE id=?", (payload.language, user["id"]))
    user["language"] = payload.language
    return user


# ---------------------------------------------------------------- RAG: documents and questions
@app.get("/api/documents")
def list_documents(request: Request):
    return [{"name": name, "chunks": count} for name, count in sorted(request.app.state.retriever.sources().items())]


@app.post("/api/documents", status_code=201)
async def upload_document(request: Request, file: UploadFile = File(...), user: dict = Depends(current_user)):
    name = Path(file.filename or "").name
    if not name:
        raise HTTPException(status_code=400, detail="The file has no name.")
    if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
        raise HTTPException(status_code=400, detail="Upload a PDF, TXT or MD file.")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {settings.max_upload_mb} MB.")
    retriever: Retriever = request.app.state.retriever
    if name in retriever.sources():
        raise HTTPException(status_code=409, detail=f"'{name}' is already in the knowledge base.")
    try:
        chunks = build_chunks(name, data, settings.chunk_words, settings.chunk_overlap)
    except Exception as exc:  # pypdf raises several error types for broken files
        raise HTTPException(status_code=400, detail=f"Could not read this file: {exc.__class__.__name__}") from exc
    if not chunks:
        raise HTTPException(status_code=422, detail="No readable text found. Scanned PDFs need OCR before upload.")
    (UPLOADS_DIR / name).write_bytes(data)
    retriever.add(chunks)
    return {"name": name, "chunks": len(chunks)}


@app.post("/api/ask")
def ask(payload: AskRequest, request: Request, user: dict = Depends(current_user)):
    try:
        return request.app.state.rag.answer(payload.question)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/llm-check")
def llm_check(request: Request, user: dict = Depends(current_user)):
    """Confirms the AI model API key and model name work with one small request."""
    return check_connection(request.app.state.llm)


# ---------------------------------------------------------------- disease image classification
@app.post("/api/disease/predict")
async def predict_disease(file: UploadFile = File(...), user: dict = Depends(current_user)):
    classifier = get_disease_classifier()
    if classifier is None:
        raise HTTPException(status_code=503, detail="The disease model is not trained yet. See the README, step 5.")
    if not (file.content_type or "").startswith("image/") and Path(file.filename or "").suffix.lower() not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Upload a JPG or PNG photo of a leaf.")
    data = await file.read()
    if len(data) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Photo is larger than 8 MB.")
    try:
        predictions = classifier.predict(io.BytesIO(data), top_k=3)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Could not read this image. Try a different photo.") from exc
    metrics = MODELS_DIR / "disease_metrics.json"
    accuracy = json.loads(metrics.read_text(encoding="utf-8")).get("test_accuracy") if metrics.exists() else None
    return {"predictions": predictions, "model_test_accuracy": accuracy, "disclaimer": DISEASE_DISCLAIMER}


# ---------------------------------------------------------------- crop recommendation
@app.post("/api/crops/recommend")
def recommend_crop(payload: CropRequest, user: dict = Depends(current_user)):
    recommender = get_crop_recommender()
    if recommender is None:
        raise HTTPException(status_code=503, detail="The crop model is not trained yet. See the README, step 5.")
    return recommender.recommend(payload.model_dump())


# ---------------------------------------------------------------- soil analysis
@app.post("/api/soil/analyze")
def analyze_soil(payload: SoilRequest, user: dict = Depends(current_user)):
    return soil.analyze(payload.nitrogen, payload.phosphorus, payload.potassium, payload.ph, payload.organic_carbon)


# ---------------------------------------------------------------- weather
@app.get("/api/weather")
def get_weather(request: Request, lat: float, lon: float, user: dict = Depends(current_user)):
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise HTTPException(status_code=400, detail="Latitude or longitude is out of range.")
    try:
        raw = weather.fetch_forecast(lat, lon, settings.weather_base_url)
    except weather.WeatherError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    days = weather.parse_days(raw)
    alerts = weather.build_alerts(days)
    for alert in alerts:
        _notify(request.app.state.db, user["id"], alert["kind"], alert["title"], alert["body"])
    return {
        "source": "Open-Meteo",
        "current": raw.get("current", {}),
        "daily": days,
        "alerts": alerts,
    }


# ---------------------------------------------------------------- market prices
@app.get("/api/market")
def get_market(request: Request, commodity: str, user: dict = Depends(current_user)):
    if not settings.datagov_api_key:
        raise HTTPException(status_code=503, detail="Market prices need a free data.gov.in key. Set DATAGOV_API_KEY in backend/.env.")
    commodity = commodity.strip()
    if len(commodity) < 2:
        raise HTTPException(status_code=400, detail="Enter a commodity name, for example Tomato.")
    try:
        rows = fetch_prices(commodity, settings.datagov_api_key, settings.datagov_resource_id)
    except MarketError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    summary = summarize(rows)
    db: Database = request.app.state.db
    for watch in db.all("SELECT * FROM price_watches WHERE user_id=? AND LOWER(commodity)=LOWER(?)",
                        (user["id"], commodity)):
        if summary["max_modal"] is not None and summary["max_modal"] >= watch["threshold"]:
            _notify(db, user["id"], "price_alert", f"{commodity} price alert",
                    f"{commodity} reached Rs {summary['max_modal']:.0f} per quintal, at or above your target of Rs {watch['threshold']:.0f}.")
    return {"source": "data.gov.in (Agmarknet)", "commodity": commodity,
            "records": sorted(rows, key=lambda r: -r["modal"])[:50], "summary": summary}


@app.post("/api/market/watch", status_code=201)
def add_watch(payload: WatchRequest, request: Request, user: dict = Depends(current_user)):
    request.app.state.db.execute(
        "INSERT INTO price_watches (user_id, commodity, threshold, created_at) VALUES (?, ?, ?, ?)",
        (user["id"], payload.commodity.strip(), payload.threshold, datetime.now(timezone.utc).isoformat()),
    )
    return {"ok": True}


# ---------------------------------------------------------------- finance
@app.post("/api/finance/calculate")
def calculate_finance(payload: FinanceRequest, user: dict = Depends(current_user)):
    costs = {
        "seed": payload.seed_cost, "fertilizer": payload.fertilizer_cost, "pesticide": payload.pesticide_cost,
        "labour": payload.labour_cost, "irrigation": payload.irrigation_cost, "other": payload.other_cost,
    }
    try:
        return finance.crop_economics(
            payload.area_acres, payload.yield_per_acre, payload.price_per_quintal, costs,
            payload.lease_per_acre, payload.loan_amount, payload.loan_rate_pct, payload.loan_years,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ---------------------------------------------------------------- notifications
@app.get("/api/notifications")
def list_notifications(request: Request, user: dict = Depends(current_user)):
    rows = request.app.state.db.all(
        "SELECT id, kind, title, body, read, created_at FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 50",
        (user["id"],))
    return {"unread": sum(1 for r in rows if not r["read"]), "items": rows}


@app.post("/api/notifications/{notification_id}/read")
def mark_read(notification_id: int, request: Request, user: dict = Depends(current_user)):
    request.app.state.db.execute("UPDATE notifications SET read=1 WHERE id=? AND user_id=?", (notification_id, user["id"]))
    return {"ok": True}


@app.post("/api/notifications/read-all")
def mark_all_read(request: Request, user: dict = Depends(current_user)):
    request.app.state.db.execute("UPDATE notifications SET read=1 WHERE user_id=?", (user["id"],))
    return {"ok": True}
