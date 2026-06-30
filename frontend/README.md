# Aastha ERP Assistant — React Frontend

The web UI for the Aastha ERP AI chatbot. It calls the Python backend API
(`/chat` and `/export`).

## Prerequisites
- Node.js 18+ (you have v24)
- The backend API running (see project root, `INTEGRATION.md`):
  ```powershell
  & C:\Glowstar_chatbot\venv\Scripts\python.exe -m uvicorn app.api.main:app --reload
  ```

## Run (development)
```powershell
cd frontend
npm install
npm run dev
```
Open the URL it prints (default http://localhost:5173).

## Configure the API URL
By default it calls `http://localhost:8000`. To point elsewhere, create
`frontend/.env`:
```
VITE_API_URL=http://your-server:8000
```

## Build for production
```powershell
npm run build      # outputs to frontend/dist
npm run preview    # serve the build locally to test
```

## What it does
- Chat box → sends the question to `POST /chat`
- Shows the answer, plus a collapsible "See the SQL" panel for transparency
- Header shows whether the backend API is online
- (Backend handles all safety: read-only queries only)
