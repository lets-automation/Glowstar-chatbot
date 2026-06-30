# Aastha ERP AI Chatbot

A read-only AI agent that answers natural-language questions about the
Aastha ERP (diamond/jewellery manufacturing) by querying its SQL Server
database. Built in phases.

## Project Structure (modular)

```
Glowstar_chatbot/
├── .env                      # secrets & DB settings (NOT committed)
├── requirements.txt          # Python dependencies
├── README.md
│
├── app/                      # main application package
│   ├── config.py             # central settings (reads .env)
│   │
│   ├── database/             # DB connection & query helpers
│   │   └── connection.py     # SQL Server engine (Windows auth)
│   │
│   ├── schema/               # Phase 2: schema extraction + glossary
│   ├── agent/                # Phase 3: Claude Text-to-SQL agent
│   ├── api/                  # Phase 4: FastAPI /chat endpoint
│   └── core/                 # shared helpers, guardrails, safety
│
└── tests/                    # tests
    └── test_connection.py    # Phase 1 DB connection test
```

## Setup

```powershell
# 1. Create & activate virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure .env (DB settings + Anthropic key)
```

## Phase Status

- [x] **Phase 1** — Environment & Database Connection
- [x] **Phase 2** — Schema Extraction & Context Layer
- [x] **Phase 3** — Agent Core (Text-to-SQL) — LLM: **Groq** (gpt-oss-120b); live-verified
- [x] **Phase 4** — API Layer (FastAPI + CORS)
- [x] **Phase 5** — Guardrails, Safety & Accuracy (17/17 count questions verified live)
- [x] **Phase 6** — Artifact Generation (Excel/PDF/charts + /export)
- [~] **Phase 7** — Semantic Search (scaffold; optional, needs Voyage+Pinecone keys)
- [x] **Phase 8** — Demo UI (Streamlit) & Handover docs (INTEGRATION.md)

## Run the connection test

```powershell
python -m tests.test_connection
```

## Run the full app

Backend API (Python):
```powershell
& C:\Glowstar_chatbot\venv\Scripts\python.exe -m uvicorn app.api.main:app --reload
# http://localhost:8000/docs
```

Frontend (React, in a second terminal):
```powershell
cd frontend
npm install   # first time only
npm run dev
# http://localhost:5173
```

The React app calls the API; the API runs the Groq-powered agent against
the AasthaErp database. LLM provider is set in `.env`
(`GROQ_API_KEY`, `GROQ_MODEL`).
