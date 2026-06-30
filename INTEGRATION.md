# Integration & Handover Guide

How to deploy the Aastha ERP AI Chatbot backend and connect it to the
client's React frontend and live database.

---

## 1. What this is

A **read-only** AI assistant backend. It exposes a REST API. The client's
React app calls the API; the API asks Claude, which queries the AasthaErp
SQL Server database and returns plain-English answers (and optional
Excel/PDF/chart exports).

It does **not** modify any data. It does **not** include a production UI.

---

## 2. Requirements on the host machine/server

- Windows (or Linux with the SQL Server ODBC driver)
- Python 3.11+
- **ODBC Driver 18 for SQL Server**
- Network access to the AasthaErp SQL Server
- A **Groq API key** (the LLM provider; get one at https://console.groq.com)

---

## 3. Setup

```powershell
# from the project folder
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Edit **`.env`**:
```
# Point at the LIVE database
DB_SERVER=YOUR_SQL_SERVER_HOST          # e.g. 192.168.1.10 or SERVER\INSTANCE
DB_NAME=AasthaErp
DB_DRIVER=ODBC Driver 18 for SQL Server

# LLM provider (Groq)
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
```
> If the live DB uses a SQL login instead of Windows auth, the connection
> string in `app/database/connection.py` needs UID/PWD added — ask the
> developer to switch it; it's a small change.

Verify the DB connection:
```powershell
python -m tests.test_connection
```

---

## 4. Run the API

```powershell
python -m uvicorn app.api.main:app --host 0.0.0.0 --port 8000
```
- Health check: `http://SERVER:8000/health`
- Interactive docs: `http://SERVER:8000/docs`

For production, run behind a process manager / reverse proxy (e.g. IIS,
nginx) and restrict CORS (see step 6).

---

## 5. API the React app calls

### POST `/chat`
Request:
```json
{ "question": "How many packets are on jangad?" }
```
Response:
```json
{
  "answer": "There are 12,345 packets currently on jangad.",
  "sql_used": ["SELECT TOP 1000 COUNT(*) FROM tblJangadPackets ..."],
  "rows_returned": 1
}
```

### POST `/export`  (download a file)
Request:
```json
{ "query": "SELECT TOP 50 Shape, COUNT(*) AS Cnt FROM tblPacketHistory GROUP BY Shape",
  "format": "excel" }
```
Returns the file (Excel / PDF / PNG) for the browser to download.
`format` can be `"excel"`, `"pdf"`, or `"chart"` (charts also accept
`x_col` and `y_col`).

### React fetch example
```javascript
const res = await fetch("http://SERVER:8000/chat", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ question }),
});
const data = await res.json();   // { answer, sql_used, rows_returned }
```

---

## 6. Before production (important)

- **Tighten CORS**: in `app/api/main.py`, change `allow_origins=["*"]` to
  the client's real React domain(s).
- **Protect the API**: add authentication (e.g. an API key/JWT) so only the
  React app can call it.
- **Read-only DB user**: point `.env` at a SQL login that only has SELECT
  permission — defense in depth on top of the app's own read-only guard.
- **Costs**: LLM usage is billed to the client's Groq account (set
  `ANTHROPIC_API_KEY` and switch the agent back to Claude if preferred).

---

## 7. Internal demo (optional)

To show the assistant without React:
```powershell
streamlit run demo/streamlit_app.py
```
Opens a chat page in the browser. Needs `ANTHROPIC_API_KEY` set.

---

## 8. Safety summary

- Only `SELECT` runs; INSERT/UPDATE/DELETE/DROP and commands are blocked in
  `app/core/sql_guard.py` and re-checked in `app/database/runner.py`.
- Every query is row-capped and time-limited.
- System/login tables (`AspNet*`, etc.) are hidden from the agent.
- Every question + SQL is logged to `logs/agent.log`.
