# AgriAssist: A Multilingual-Ready GenAI Advisory Chatbot for Farmers

AgriAssist answers farming questions with retrieval-augmented generation (RAG). It searches a knowledge base of agriculture documents, sends the most relevant passages to a language model, and returns an answer with numbered citations. Questions that describe a poisoning or other emergency, or that the knowledge base cannot answer reliably, are escalated to a human expert. Risky questions never reach the language model.

## Features

- **RAG pipeline:** PDF/TXT/MD ingestion, chunking, TF-IDF retrieval, grounded generation.
- **Citations:** every answer lists the source file and page for each passage used.
- **Safety escalation:** risk-term detection runs before generation. Low-confidence questions are escalated.
- **Works without an AI key:** with `LLM_PROVIDER=none`, the app shows the most relevant passages instead of generated text.
- **Document upload:** add PDFs from the browser; they are indexed immediately.
- **Mobile-friendly UI:** single-column layout on phones, no horizontal scrolling.
- **Tests:** 27 automated tests cover ingestion, retrieval, escalation, the LLM client and the API.

## Project structure

```
agriassist/
├── backend/            FastAPI API and RAG pipeline
│   ├── app/            config, ingest, retriever, safety, llm, rag, main
│   ├── data/docs/      sample knowledge base (replace with real guides)
│   ├── tests/          pytest suite
│   ├── requirements.txt
│   └── .env.example
├── frontend/           static web app (HTML, CSS, JavaScript)
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── config.js       backend URL
├── DEPLOYMENT.md       GitHub and hosting guide
└── README.md
```

## 1. Prerequisites

- Python 3.10 or newer (`python3 --version`)
- A terminal (Command Prompt or PowerShell on Windows, Terminal on macOS/Linux)
- Optional: an API key from OpenAI (or any OpenAI-compatible provider) or Google Gemini

## 2. Install dependencies

```bash
cd agriassist/backend
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

## 3. Configure environment variables

```bash
cp .env.example .env          # Windows: copy .env.example .env
```

Open `backend/.env` and set:

| Variable | Purpose | Example |
|---|---|---|
| `LLM_PROVIDER` | `openai`, `gemini` or `none` | `openai` |
| `LLM_API_KEY` | Your API key | `sk-...` |
| `LLM_MODEL` | Optional model name | `gpt-4o-mini` |
| `CORS_ORIGINS` | Frontend URLs allowed to call the API | `http://localhost:5500` |
| `MIN_CONFIDENCE` | Escalation threshold (0 to 1) | `0.10` |

To run without an AI model, set `LLM_PROVIDER=none`. The app then returns the most relevant passages with citations.

## 4. Run the backend

From the `backend` folder with the virtual environment active:

```bash
uvicorn app.main:app --reload --port 8000
```

Check it works:

- Health: http://localhost:8000/api/health
- Interactive API docs: http://localhost:8000/docs
- AI connection test: http://localhost:8000/api/llm-check (should say `"ok": true` when your key is valid)

## 5. Run the frontend

Open a second terminal:

```bash
cd agriassist/frontend
python -m http.server 5500
```

Open **http://localhost:5500** in your browser. The page should show "Online" at the top.

The frontend reads its backend address from `frontend/config.js`. Locally this is `http://localhost:8000`.

## 6. Test the complete application

### Automated tests

```bash
cd agriassist/backend
pytest -q
```

Expected output: `27 passed`.

### Manual checklist

| # | Check | How | Expected |
|---|---|---|---|
| 1 | Backend starts | `uvicorn` command above | "Application startup complete" in the terminal |
| 2 | API connection | Open `/api/llm-check` | `"ok": true` (or `"ok": false` with a clear reason if `LLM_PROVIDER=none`) |
| 3 | PDF ingestion | Upload any text-based PDF in the sidebar | Green toast message and the file appears in the list |
| 4 | Retrieval | Ask "How do I control early blight on tomato leaves?" | A relevant tomato passage is shown in Sources |
| 5 | Citations | Expand "Sources" under an answer | Each source shows file name, page and snippet |
| 6 | Low-confidence escalation | Ask "What is the capital of France?" | Yellow/red escalation card, no answer text |
| 7 | Risky query blocked | Ask "My son swallowed pesticide, what now?" | Emergency message with 112 advice, and the model is not called |
| 8 | Mobile layout | Open the page on a phone or in browser developer tools at 390 px width | Single column, no horizontal scrolling, all buttons tappable |

To test on a phone on the same Wi-Fi network, find your laptop's IP address (for example `192.168.1.20`), run the frontend with `python -m http.server 5500 --bind 0.0.0.0`, and open `http://192.168.1.20:5500` on the phone. Add `http://192.168.1.20:5500` to `CORS_ORIGINS` in `backend/.env` and restart the backend.

## 7. Replace the sample knowledge base

The files in `backend/data/docs/` are sample text written for this demo. Before a real or public demo, replace them with official material such as:

- Krishi Vigyan Kendra (KVK) and ICAR crop guides
- State agriculture department advisories
- Pesticide and fertilizer labels

Only use material you have the right to use. Restart the backend after adding files, or upload PDFs from the browser.

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| `Cannot reach the AgriAssist server` in the page | Backend is not running, or `config.js` points to the wrong address |
| CORS error in browser console | Add the frontend URL to `CORS_ORIGINS` and restart the backend |
| `"ok": false` from `/api/llm-check` | Check the key, the provider name and the model name in `.env` |
| `Port 8000 already in use` | Use another port, for example `--port 8001`, and update `config.js` |
| `No readable text found` on upload | The PDF is scanned. Run OCR first (for example with OCRmyPDF) |
| `pytest` not found | Activate the virtual environment first |

## 9. How it works

1. **Ingest:** documents are read, split into 120-word chunks with a 20-word overlap, and indexed with TF-IDF.
2. **Retrieve:** the question is matched against the index; the top 4 passages are returned with similarity scores.
3. **Decide:** if the question matches a risk term, or the best score is below `MIN_CONFIDENCE`, the bot escalates and stops.
4. **Generate:** otherwise the passages and question go to the language model with instructions to answer only from them and to cite passage numbers.
5. **Respond:** the answer is shown with its sources. If the model fails, the app shows the retrieved passages instead.

### Calibration note

The default threshold of 0.10 was chosen by testing sample questions on the sample knowledge base. Questions about the crops and topics in the knowledge base scored about 0.11 to 0.35. Off-topic questions scored 0.08 or below. Re-check the threshold after you change the documents.

## 10. Known limitations

- Retrieval uses TF-IDF with light stemming. It works well for English keywords but is weaker for paraphrases and for questions written in Hindi or Kannada. Native-language answers depend on the language model. Adding multilingual embeddings is the next step.
- The knowledge base is small and was written for the demo. Answers are only as good as the documents.
- Uploaded files are stored on the server's disk. Free hosting plans may delete them on restart, so keep a copy of important documents in `backend/data/docs/`.
- AgriAssist gives advice only. It cannot diagnose plant diseases from photos, and it does not replace a local expert.

---

## Smart Agriculture Platform: added features (version 2)

| Feature | Where | How it works |
|---|---|---|
| Registration and login | `/api/auth/*`, login screen | Passwords hashed with PBKDF2-SHA256 (200,000 rounds); signed bearer tokens (HMAC-SHA256, valid for `TOKEN_HOURS`) |
| Language switching | header selector | English, Hindi, Kannada; choice saved to the account and the browser |
| AI question answering and RAG | Ask AI tab | TF-IDF retrieval over the knowledge base, numbered citations; escalation before generation |
| PDF ingestion | Ask AI, "Add a document" | PDF/TXT/MD parsed by pypdf, chunked, indexed immediately |
| Leaf disease detection | Leaf disease tab | Logistic regression on HOG + HSV features, trained on real PlantVillage leaf images (10 classes) |
| Crop recommendation | Crop advice tab | Random forest on N, P, K, temperature, humidity, pH, rainfall, with explanations of out-of-range inputs |
| Soil analysis | Soil test tab | Rule-based fertility ratings for N, P, K, pH and organic carbon |
| Weather | Weather tab | Open-Meteo 7-day forecast (no key needed), rule-based heavy rain, heat and cold alerts |
| Mandi (market) prices | Mandi prices tab | data.gov.in Agmarknet prices (needs a free key), price alerts |
| Financial calculations | Finance tab | Cost, revenue, profit, return on cost, break-even, loan EMI |
| Notifications | bell icon, Alerts tab | Stored per user; created by weather, price and welcome events |

### Setup for the new features

1. Train the ML models (images and CSV are not included in the zip):

   ```bash
   cd backend
   # PlantVillage: download the "raw/color" folder from https://github.com/spMohanty/PlantVillage-Dataset
   python scripts/train_disease.py --data /path/to/PlantVillage/raw/color --per-class 400
   # Crop data: download "Crop_recommendation.csv" from Kaggle (Atharva Ingle, "Crop Recommendation Dataset"),
   # save it as backend/data/crop_recommendation.csv, then run the script. Without it, a synthetic dataset is used.
   python scripts/train_crop.py
   ```

   The trained files are already in `backend/models/` so the app runs without retraining.

2. Optional keys in `backend/.env`:
   - `DATAGOV_API_KEY`: free key from data.gov.in (register, then copy the API key). Needed for mandi prices.
   - `LLM_PROVIDER` and `LLM_API_KEY`: needed for generated answers. Without them the app shows retrieved passages.
   - `AUTH_SECRET`: a long random string. Change it before deployment.

3. Run the tests: `cd backend && pytest -q`.

### Honest notes on the models

- Leaf model: measured test accuracy is in `backend/models/disease_metrics.json` (held-out PlantVillage images, not seen in training). PlantVillage photos have plain backgrounds, so accuracy on field photos will be lower. This is the main limitation to state in the report.
- Crop model: if the public Kaggle CSV is not present, it is trained on synthetic data generated from typical agronomic ranges. Its 100% accuracy only confirms that the pipeline works. It is not evidence of real-world accuracy.
- Weather and market services need internet access and, for market prices, a key. The app shows the service error instead of invented numbers.

---

## Version 3: design and theme

- **Light and dark themes.** Use the sun/moon button in the top bar. The choice is saved in the browser; by default the page follows the device setting.
- **Layouts.** Sidebar navigation on desktop, a scrolling tab bar on tablets, and a single column on phones. The page does not scroll sideways at 390 px.
- **Contrast.** Text colours meet WCAG AA in both themes (body text at least 4.5:1).
- **Checks run for this version:** 74 pytest tests passed; 26/26 Playwright end-to-end checks passed; screenshots checked at 1280 px and 390 px in both themes.

### Environment variables (backend/.env)

| Variable | Purpose |
|---|---|
| `AUTH_SECRET` | Long random string that signs login tokens. Required before deployment. |
| `TOKEN_HOURS` | Login token lifetime in hours (default 168). |
| `DATAGOV_API_KEY` | data.gov.in key for mandi prices. |
| `WEATHER_BASE_URL` | Optional; defaults to Open-Meteo. |
| `DB_PATH` | Location of the SQLite database file. |

Note: on free hosting the SQLite database and uploaded PDFs can be lost when the service restarts or redeploys. Keep copies of important documents in `backend/data/docs/`.
