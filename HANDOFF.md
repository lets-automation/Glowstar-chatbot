# GlowStar Chatbot — Session Handoff (2026-07-03)

Text-to-SQL chatbot over the **AasthaErp** SQL Server DB for a Surat natural-diamond
manufacturer. Python FastAPI backend + Vite/React frontend, deployed with Docker.

> **Honest status: NOT production-ready yet.** The plumbing is solid, but every audit
> pass keeps finding real data-model bugs that produce confident *wrong* answers. Do
> not tell the client it's ready until the accuracy pass (below) is done. The client
> was unimpressed once already — trust is the priority.

> **⚠️ NEVER run destructive SQL / resets (DELETE/DROP/TRUNCATE, `docker compose down -v`)
> against the live `history-db`. Use a throwaway database for tests.** On 2026-07-09 a
> raw `DELETE FROM chat_threads` run during testing wiped all chat history; recovered
> from browser localStorage. Safeguard added: the `history-backup` service auto-dumps the
> chat DB every 6h to `./backups/history/`. **Restore chat history:**
> ```
> docker compose exec history-backup pg_restore -h history-db -U glowstar \
>   -d glowstar_history --clean --if-exists /backups/history-YYYYMMDD-HHMMSS.dump
> ```
> (`--clean --if-exists` overwrites current state with the backup; `pg_restore --list
> /backups/<file>` inspects a dump without restoring.) History now has TWO independent
> backups: these dumps + each browser's localStorage copy. Verified: dumps round-trip.

---

## 1. How it runs RIGHT NOW

- **Full stack:** `docker compose up -d --build` → open **http://localhost:8080**
  - Services: `frontend` (nginx :8080, proxies `/api`→backend), `backend` (FastAPI :8000,
    non-root), `redis`. The bundled `db` container is OFF by default (behind the
    `bundled-db` profile) — the backend connects to the **real** SQL Server.
- **No login screen.** `AUTH_ENABLED=false` in `.env` (guest access). All the JWT/bcrypt
  auth code is still there, dormant — set `AUTH_ENABLED=true` to re-enable. (Login was
  removed because the chatbot will embed in the client's CRM, which handles identity.)
- **DB connection:** backend → real SQL Server via **read-only login `glowstar_ro`**
  (created on the host; reads AasthaErp, cannot write — verified). Compose sets
  `DB_SERVER=host.docker.internal, DB_USER=glowstar_ro, DB_PASSWORD=${DB_RO_PASSWORD}`.
  - The host SQL Server was opened up for this: mixed-mode auth (LoginMode=2), TCP/IP on
    1433, firewall rule. A real/client server normally already allows this.

## 2. PROVIDERS — the #1 gotcha

Editing `.env` does NOTHING to a running container. **After any `.env` change:**
```
docker compose up -d --force-recreate backend
docker compose exec backend python -c "from app.config import settings; print(settings.LLM_PROVIDER)"
```
- **groq** — free, ~500k tokens/DAY (exhausts fast when testing). **A NEW Groq key was
  just added → fresh daily limit.** Model `meta-llama/llama-4-scout-17b-16e-instruct`.
  Reliable tool-calling. **Use this for free testing.**
- **gemini** — free but **unreliable**: it silently skips the SQL tool and answers
  without querying (the anti-fabrication guard then correctly refuses). **Avoid.**
- **anthropic (Claude)** — best, most reliable. **Only ~$3 credits left — RESERVE for the
  client demo.** `claude-sonnet-4-6`.

## 3. Data-model bugs FIXED this session (7, via free static DB audit)

All in `app/agent/tools.py` (RULES) and `app/schema/glossary.py` (DATA_NOTES/JOIN_HINTS):
1. **Employee identity:** join the NUMERIC `Emp_ID → tblEmployee.ID`, GROUP BY the id.
   NEVER group/join by name — up to **9 different people share a name** (merging them
   inflated bonus totals: the "Diyora ₹4,364" bug = 3 people summed). `EmpName` in labour
   tables is a CODE, not a name — ignore it. True top bonus = PANDAV HITESH (MFG-2) 2059.88.
2. **Earnings ≠ bonus:** in `tblLabourResult`, `FinalLabour` = what a worker earns;
   `BonusAmount` = separate bonus (can be negative). 10 amount columns there — easy to confuse.
3. **Trap tables:** NEVER query `*_BKP / *Edit / *_Compare / *_Demo / *_Update / *GIA / *Temp`
   variants (stale/partial/FAKE data). `tblTimeAttendance_Demo` = 45k FAKE rows.
   Blocked by a rule AND a code filter (`_is_trap_table` in `tool_find_tables`).
4. **Attendance broken:** `tblTimeAttendance.EmpId` is 100% NULL; `UserId` matches only
   ~14% of employees. Per-employee present-days is NOT reliably answerable — the agent now
   says so honestly instead of returning empty/wrong.
5. **Count inflation:** use `COUNT(DISTINCT Packet_ID / EmpID)`, not `COUNT(*)`, on
   transactional tables (`tblIncentiveAmount` ~310 rows/employee, `tblLabourResult` ~6/packet).
6. **Date columns** differ & are misspelled per table: `tblPacket→CreDate`,
   `tblPlanMaster→CreatDate`, `tblIncentiveAmount→TransactTime`, `tblTimeAttendance→Time`,
   `tblPacketHistory→ReciveTime`, `tblPlanReport→CreatedDate`, `tblFinalPacket→CreateDate`.
7. **Sales:** `tblPacketSell` exists but is EMPTY → say "no sales data", never fabricate.

## 4. Other fixes earlier this session
- Frontend **data-loss** on switching/deleting a chat mid-stream — fixed in
  `frontend/src/runtime/useGlowstarRuntime.js` (localMsgs + `ownsUI()` gating).
- **Export crashes** on Gujarati/wide/dirty data — `pdf.py` registers DejaVuSans + wraps
  cells; `excel.py` strips XML-illegal chars.
- **Excel chart** made professional — `app/artifacts/excel.py`: category labels show
  (openpyxl `delete=False`), single blue bars, value-only labels above bars, no axis-title
  overlap, landscape fit-to-page. (Verify visually by rendering xlsx→pdf via LibreOffice →
  PyMuPDF png. LibreOffice is installed.)
- **Display rule:** KapanName/PacketNo only (never raw KapanID/PacketID); packet shown as
  `KapanName-PacketNo` ONLY when there's no separate KapanName column; no repetition.
- **Damage report** = detail rows: KapanName, Packet, EmployeeName, Dept, PreWt/NewWt/WtDiff,
  Points/Rate/Amount, DamageType, Date (uses `tblPlanReport`, `InceDamageTypeName` for type).
- anti-fabrication guard (checks `data_rows`), file_id validation, DB error handling (no raw
  leaks to client), connection pool bounded, top-level React error boundary.
- Charts: on-screen `show_chart` supports pie/bar/line; **Excel export is always a BAR chart**
  (not yet wired for pie/line export).

## 5. WHAT'S LEFT (in priority order)
- **Continue the free static data-model audit** (next: which-table/column for stock,
  production output, rejection, repair; coded-value completeness; Kapan/Packet identity
  code-vs-name check). Each pass has found real bugs — surface not exhausted.
- **THE proof step (paid):** run `tests/test_accuracy.py` + the client's REAL questions on
  **Claude**, check each answer against ground truth (independent SQL). Only this lets you
  honestly say "these answers are verified." Save a slice of the $3 for right before the demo.

### Accuracy-verification strategy (client runs on CLAUDE; 3 layers, 2026-07-09)
The fixes live in PROVIDER-INDEPENDENT places (glossary/rules/guards), so most of "will the
bugs recur on Claude" is verifiable WITHOUT spending Claude tokens:
- **Layer 1 — DONE (free, permanent):** `tests/test_regression_datamodel.py` (26 tests) LOCKS every
  data-model fix — trap-table filter, critical glossary guidance present (labour current-vs-dead,
  repair≠CRUD-log, sales-empty, Emp_ID identity, attendance-unreliable, incentive-points,
  COUNT DISTINCT), router surfaces the right tables, anti-fabrication guard fires. Proven to BITE
  (fails when a fix is removed). Runs with no DB/LLM. Any future glossary/guard edit that breaks a
  fix now goes red instead of silently regressing — on Claude too, since the guidance is identical.
- **Layer 2 — free, TODO:** re-run the 12 real questions on the current provider vs independent
  ground-truth SQL (verifies routing/logic end-to-end on the data; carries over to Claude).
- **Layer 3 — tiny paid, at handover:** one 12-question run ON Claude (~$1–2, a slice of the $3, NOT
  token-exhausting) to confirm Claude's exact SQL. Only this needs Claude; Layers 1–2 do not.
- Provider switch to Claude is a config flip (LLM_PROVIDER=anthropic + key); the Groq/Gemini
  correction-guards are harmless no-ops on Claude. Point backend at the client's LIVE DB (not the
  frozen ~25-Jun snapshot) before real testing.
- Lower-priority, flagged-not-fixed: multi-tab last-write-wins on chat history; localStorage
  quota-fallback silently dropping export data; widget CSP `img-src` could beacon data out;
  `/upload` buffers whole file before the 15MB check.

## 6. Testing & gotchas
- Tests: `venv/Scripts/python.exe -m pytest tests/ -q` → 18 pass. Needs a host Redis on
  localhost:6379: `docker run -d --name glowstar-redis-dev -p 6379:6379 redis:7-alpine`.
- **Always use the venv python** for backend scripts (system python lacks pyodbc/reportlab).
- Read-only DB access for audits: `from app.database.runner import run_select` (SELECT only).
- Windows console is cp1252 — printing ₹ or Gujarati crashes; add
  `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in test scripts.
- Port 8000 zombie processes: `taskkill /PID <pid> /T /F`.
- Key files: `app/agent/tools.py` (RULES+tools), `app/schema/glossary.py` (semantic layer),
  `app/agent/postprocess.py` (guards), `app/artifacts/*` (exports), `GLOWSTAR_KNOWLEDGE.md`
  (industry KB), `docker-compose.yml`, `.env` (+ `.env.docker.example`).

## 7. Mantra for the next session
Don't declare it "production ready." Verify against the real data, show your work, and be
honest about what's checked vs. assumed. Free static audits find bugs cheaply; the Claude
accuracy pass is what proves correctness. **Never spend a paid Claude call without asking.**

---

## APPENDIX — Static audit passes 2 & 3 (2026-07-03, free; all encoded in glossary.py)

**Pass 2 findings (verified vs real DB; 5 spot-checked end-to-end on Groq, exact matches):**
1. **REPAIR tables were MISLABELED (confident wrong-answer bug).** `tblRepairLog` &
   `tblRepairLogNew` are database CRUD/audit logs (Insert/Update/Delete on plan tables),
   NOT diamond re-polish. `tblRepairLog` is dead since Feb 2022. "How many repaired?" would
   have returned **7,753** (log rows); correct is **47** from `tblRepairCommentVision` (the
   real stone re-check table). tblRepairing/tblRepairLoss empty.
2. **PacketNo is NOT unique** — 164,573 packets, only 2,330 distinct PacketNo (PacketNo=1
   spans 842 kapans). Identity = numeric `tblPacket.ID` (=`Packet_ID`). Never group/join on
   PacketNo alone.
3. **STOCK = two meanings.** `tblStock*` = consumables/stores (pens, ink, machine tools) —
   NOT diamonds. Diamond stock/stage = `tblPacket.RunningProcess` ('IN Stock'=148,971).
4. **REJECTION → `tblJunk`** (`tblRejection` empty). Only Weight/Pcs/Packet_ID/Kapan_ID/
   CreateDate usable (Value 95% NULL, Grede 100% NULL).
5. **Production output = `tblFinalPacket`** (one row per finished packet, COUNT(*) safe).
6. Verified GOOD: KapanName unique 1:1; all coded values match glossary (Shape has ~12 rare
   extra codes now flagged non-exhaustive).

**Pass 3 findings:**
7. **LABOUR/EARNINGS table currency (fixed a stale-data bug in the OLD guidance).** The prior
   glossary sent every earnings/bonus query to `tblLabourResult` — which is HISTORICAL
   (2020→dead ~Feb 2023) and returns ~empty for 2023-2026. The CURRENT table is
   **`tblPointRateLabour`** (mid-2022→now). They OVERLAP mid-2022..Feb-2023 (same packets,
   slightly different recomputed amounts) → NEVER union/sum both (double-counts). Verified on
   Groq: total labour 2025 = **₹1,231,815.58** (exact ground-truth match), routed to the
   right table, GROUP BY numeric Emp_ID.
8. **RATE CARDS are config — don't SUM them.** `tblLabourRate` (3.4M), `tblReportRate` &
   `tblBonusRate` (1.5M each) are rate-lookup cards; SUM(Amount) is meaningless. Use
   `tblPointRateLabour.FinalLabour` for money paid. tblReportRate/tblBonusRate store Shape as
   a comma-list → match with LIKE.
9. **JANGAD by party/branch** = `tblJangad` header (FromParty/ToParty, TransType, Carats,
   Amount, BranchId); `tblJangadPackets` = packet lines (IsReceived=0 = still out). `tblParty`
   = party master.
10. **ORIGIN/MINE** are text inline on `tblKapan` (RoughOrigin = country, Mine = source) — no
    join needed; the masters are just dropdowns.

*Known non-data quirk:* Groq Scout sometimes narrates the SQL instead of presenting result
rows for list questions (the routing is still correct). Claude does not do this.

**Pass 4 findings (2026-07-03, free; all encoded in glossary.py):**
11. **INCENTIVE money column is DEAD (another stale-column bug in the OLD guidance).**
    `tblIncentiveAmount.Credit`/`Debit` (₹) are legacy — populated only to 2019, 100% NULL
    from 2020 on. The old glossary said "Credit (amount earned)" → returns nothing for recent
    years. The LIVE measure is a POINTS ledger: `CreditPoints` (earned) / `DebitPoints`
    (deducted, negative), by TransactTime. Use `SUM(CreditPoints)` for "incentive earned";
    net = + DebitPoints. Report POINTS, not ₹. Not zero-sum (2025 debits slightly > credits).
12. **`tblEmpGIABonus` = one-time 2019 batch** (all rows Apr–Oct 2019, per-packet MFG/PLS/GIA
    plan amounts) — NOT a live bonus stream.
13. **JANGAD direction:** `tblJangad.TransType` 'Issue' = out, 'Receive' = return (not a sale).
    Header "currently out" = `TransType='Issue' AND IsReceived=0`. Packet "still out" =
    `tblJangadPackets WHERE IsReceived=0`, use `COUNT(DISTINCT PacketId)` (~140k distinct vs
    ~190k rows — packets get re-issued). ~534 packets currently out.
14. **Departments are a FLAT list** (`tblDepartMent` ~92 rows, no parent/child); `OriginType`
    loosely buckets variants (Blocking + Blocking Auto → 'Blocking'). Confirms no 'Cutting' dept.

*Pass-4 encoding verified: glossary renders clean (~29k chars), 18/18 tests pass. Not
re-validated end-to-end on Groq (passes 1–3 already proved the mechanism; conserving tokens).*

**Pass 5 findings (2026-07-03, free; all encoded in glossary.py):**
15. **PACKET JOURNEY** = `tblPacketHistory` (5.5M rows, ~34 per packet — NEVER COUNT(*)). It
    holds the completed process steps (Process, EmpId→ToEmpId, Weight, WightLoss, ReciveTime)
    — the "where has this packet been / who handled it / when" table; ORDER BY ReciveTime.
    `tblPacketIssue` (5.5M) is the issue-out companion. A packet's CURRENT stage is still
    `tblPacket.RunningProcess`.
16. **`tblLabour_MW` is mostly empty** — monthly WorkPoint summary (2021–24) but the Final/Adjust
    (wage) columns are 100% NULL. Do NOT use it for monthly wages; aggregate
    `tblPointRateLabour.FinalLabour` by month instead.
17. **`tblOriginWiseLabour` = another rate CARD** (Origin+attrs→Amount) — don't SUM.
18. **`tblBox`** = incoming rough box/lot register (BoxNo, Article, TotalWeight/Pcs);
    **`tblKapanChallan`** = KapanName→ChallanNo lookup.

*Encoding verified: glossary renders clean (~32k chars), 18/18 tests pass. Not re-validated on
Groq (conserving tokens).*

**Context-size note:** the glossary/data-notes block is now ~32k chars (was ~24k pre-audit).
It's included on every question, so watch Groq token cost and possible attention dilution;
consider prioritizing/trimming the notes (or making them question-relevant) before adding much
more.

**Pass 6 findings (2026-07-03, free; all encoded in glossary.py):**
19. **`tblParam` = APP CONFIG** key-value store (KapanHold/MKBApprove…), NOT diamond data —
    mild trap (its name resembles "packet parameters", which are actually in
    `tblPacketParameters`).
20. **`tblPacketParameters`** = per-packet measured proportions (DiaAvg, TablePer, DepthPer,
    CrAng, PavAng, Ratio). Its GIA/IGI/AGS/HRD columns hold that lab's CUT GRADE ('GIA-V'),
    not a report id; its Symmetry column is unreliable → use `tblFinalPacket.Symmetry`.
21. **`tblPctChecker`** = who MADE (MfgEmpId) & who POLISHED (PolishEmpId) each packet — use
    for "who made/polished packet X".
22. **Jangad = outsourced job-work too:** `tblJangadProcess` (process + party: Green Sawing,
    Ghisi, Water Jet, Galaxy, Fancy) and `tblJangadRate` (per-party per-process rate).

**⚡ EFFICIENCY finding (worth a code fix).** `app/schema/context.py::build_schema_context()`
ALWAYS appends the FULL glossary (`render_glossary_text` + `render_data_notes`, now ~33k chars /
~8k tokens) on EVERY question — only per-table COLUMNS are router-filtered. This fixed cost
contributed to hitting the Groq **500k-tokens/day** cap during validation. Recommended fix:
make `TABLE_NOTES` router-aware (include a table's note only when that table is selected) and/or
gate `JOIN_HINTS`/`DATA_NOTES` by question keywords. Would cut per-call tokens substantially.

*Pass 1–4 fixes validated end-to-end on Groq (exact ground-truth matches). Pass-5 agent-
validation was deferred (daily Groq cap hit mid-run); its facts are ground-truthed and the
routing mechanism is proven. Glossary renders clean (~33k chars), 18/18 tests pass throughout.*

**Pass 7 findings (2026-07-04, free; encoded in glossary.py, validated on Groq):**
23. **LEAVE is answerable (new capability)** — `tblLeaveReport` (EmpID, LeaveDate_From/To,
    IsApproved, Reason; 20k rows, live). "Who took the most leave / leaves this month" → JOIN
    tblEmployee, filter dates, IsApproved=1. `LeaveTypeID` is an un-decoded code. Validated: top
    leave-taker 2026 = SANGANI MAHESHBHAI (MFG-4, 29). NOTE: this covers LEAVE only — present-days
    attendance is still not answerable.
24. **`tblEmployeeTimeAttandance` is NOT attendance** — a gate-pass/receipt register (PassNo/
    PassCode; InTime/OutTime ~89% empty, "employees" are parties). Name-trap; don't use for attendance.
    (tblKapanValue = per-kapan yield not ₹; tblChkImprovement = niche checker-improvement — noted, not encoded.)

**Deferred pass-5 items now validated on Groq (ground-truth exact):** packet journey
(`tblPacketHistory`, `COUNT(DISTINCT Packet_ID)` = 141,640 through Laser); 2024 monthly wages
from `tblPointRateLabour` (Mar ₹103,623.93), NOT the empty `tblLabour_MW`.

**⚠️ Groq Scout quirk is recurring (~2 of 11 tested questions):** on some list/ranking questions
Scout NARRATES the SQL in its answer text WITHOUT calling run_sql (no data shown). The table
*routing* is always correct, but the user sees no result. This is a real demo-quality risk →
**do the client demo on Claude**, or try a different Groq model (`.env` lists
`llama-3.3-70b-versatile`).

**Audit status after 7 passes:** 23 findings encoded; 3 were confident wrong-answer bugs in the
prior guidance (repair→CRUD-log, labour→dead `tblLabourResult`, incentive→dead `Credit`).
Static-audit returns are now small. **The paid Claude accuracy pass vs independent ground truth is
the highest-value next step — ask before spending the ~$3.** Also open (free): the router-aware
glossary efficiency fix (context is ~34k chars, always-on).

---

## APPENDIX — Provider testing + narrate-quirk fix (2026-07-07)

**Code fix (`app/agent/groq_backend.py`):** the "narrate-quirk" guard. Scout sometimes writes a
`SELECT` in its reply WITHOUT calling `run_sql`, so no query runs and the user sees no data. New
`_looks_like_unrun_sql()` detects a reply that embeds `SELECT…FROM` when nothing has run yet (and
it isn't a file-only answer) and forces ONE corrective round with `tool_choice="required"`, telling
the model to run the EXACT query it wrote. Result: quirk-prone list/ranking questions went from
~1/3 to **3/3 execute-and-show-data**. Tests still 17 pass / 1 skip.

**Free-provider benchmark (all fail for a *reliable* demo):**
- **Scout** (`llama-4-scout`, 30k TPM) — the only free model whose request FITS the ~18k-token
  context. Works, but **non-deterministic even at temperature 0**: one run wrote a WRONG incentive
  aggregation (10,493), the next wrote the correct one (PRADIP KASODARIYA 4201.6). Fine for
  routing/logic dev-testing; NOT trustworthy for exact numbers.
- **`llama-3.3-70b-versatile`** — **unusable at current context**: 12k tokens/min limit < 18k-token
  request → instant `413 Request too large`. Would need the efficiency fix first.
- **Gemini 2.5-flash** — routes correctly but flaky (503 overloads, occasional confusion) and only
  20 requests/day.

**⇒ Do the CLIENT DEMO on Claude** (accurate + deterministic; that's what the reserved ~$3 is for).
Free models are for development testing only.

**Why the efficiency fix is non-trivial (don't do it naively):** `build_schema_context()` always
appends the full glossary; the router `select_tables()` only picks from the 23-table `KEY_TABLES`.
Simply dropping the all-table-notes dump would delete guidance for noted tables NOT in KEY_TABLES
(`tblRepairCommentVision`, `tblLeaveReport`, `tblPacketParameters`, `tblPctChecker`, …). The proper
fix: add those tables to `KEY_TABLES` AND make notes render only for selected tables, then
re-validate every prior fix on Groq. (Attempted the naive version this session and reverted it.)

---

## APPENDIX — Client's 12 test questions: checked + fixed (2026-07-09)

Checked all 12 real client questions against the live data. Findings + fixes (all validated on Groq):
- **Most "no result" = frozen test copy.** Data ends ~25 Jun 2026 (labour/MFG ~5 Jun), server clock
  = July → "today"/"this month" return empty HERE only; fine on the client's live server.
- **No payroll data (raise with client).** No basic salary / overtime / deductions anywhere — ERP is
  piece-rate. Bot now says those aren't tracked and **offers the piece-rate labour + bonus** instead
  (`SALARY/PAYROLL` data note). Explicit basic/OT/deductions request → honest "not tracked".
- **"Manufacturing/MFG department" → `DepartmentName LIKE 'MFG%'`** (was matching a literal
  'Manufacturing' → 0 rows). Fixed in the DEPARTMENTS hint. Validated: May-2026 MFG salary returns
  real per-employee numbers + a chart.
- **Production** defined (finished packets; dept-wise = GROUP BY DepartmentName, not one bucket) —
  fixed the "MGST 171,764" garbage. **MFG loss** must be derived (RoughWt−PolishedWt); labour
  LossWeight is NULL for MFG.
- **GIA** current source = `tblFinalPacket.Lab='GIA'` / `tblPlanMaster RapVer='GIA'`;
  `tblLabourResultGIA` is stale (2024). Q8/Q9 plan comparisons are buildable but **need the client to
  confirm which RapVer stage = "Marker Approved"** first.
- **Kapan NS26** exists → finish/analysis reports feasible.

**⚡ CHART FIX (`app/agent/postprocess.py`).** Charts now render **proactively** for any categorical
summary (a text-label column + ≤4 columns + ≥2 rows; displays top 25) — previously the server-side
backstop only fired when the word "chart/graph/plot" was in the question, and the free model skipped
drawing charts itself. Also de-dupes the occasional double-identical-chart. Validated: "Show the
department-wise production summary" and "…salary for May 2026" both auto-render one chart.

*Ops note:* Groq daily cap hit during validation → swapped `.env` to the **second GROQ_API_KEY**
(line 26 active, line 25 commented). Both keys are valid; the first resets daily.

---

## APPENDIX — Dashboard artifact feature (2026-07-09, built + verified)

**What:** Claude-artifacts-style analytics dashboards rendered inline in the chat (KPI stat tiles
with ▲/▼ deltas + line trend + horizontal-bar breakdown + pie), like the screenshot the user showed.
**Trigger:** questions containing *analytics / overview / dashboard / analysis* (e.g. "Give me an
analytics overview of our production this year", "Kapan NS26 analysis").

**How it works (engine approach — required for weak free models):**
- `app/agent/widget.py`: new `SHOW_DASHBOARD_TOOL_SPEC` + `build_dashboard_html()` — the model
  supplies ONLY data (tiles + sections) from its run_sql results; our engine renders guaranteed-valid
  HTML (Chart.js for line/bar/pie, pure-CSS bars for horizontal_bar, Indian digit grouping via
  `_fmt_indian`, host CSS variables → auto light/dark).
- Wired into ALL 3 backends (groq/gemini/anthropic) alongside show_chart.
- **Dashboard-nudge guard** (groq + gemini): if the question asked for analytics but the model
  finished without calling show_dashboard (and sql ran), one corrective round is injected — same
  proven pattern as the narrate-quirk guard. Claude won't need it.
- **Groq tool-arg 400 retry**: a rejected tool call (e.g. labels as numbers) now retries once with
  the validation error instead of failing the turn.

**Verification done (no Claude spent):**
- Unit + injection + regression suite (scratchpad `render_dash.py`) — all pass; pytest 17/1 skip.
- **Adversarial multi-agent review (13 agents) found 6 real defects — ALL FIXED:** ①
  `<!--<script>` script-data-double-escape breakout (widget DoS; also patched in the pre-existing
  `build_chart_html`) → all `<` in embedded JSON now `<`; ② hbar scaled against hidden
  truncated tail (bars flattened) → vmax over rendered rows + "+N more not shown"; ③ double-escaped
  series fallback; ④ `-0` display; ⑤ int corruption >2^53 via float(); ⑥ `None` rendering as text
  'None'. Pie >8 slices → top-7 + "Other" (sum-exact).
- **E2E on Gemini (3rd key, local):** "analytics overview of production this year" → 3 sensible
  queries → dashboard rendered → headless-Edge screenshot matches the target design (verified
  visually, light + dark).
- Docker backend rebuilt; feature is LIVE at localhost:8080 (provider=gemini, fresh key #2).

**Budget state after this session:** BOTH Groq keys at daily cap (rolling reset ~1h); Gemini key#2
in container (~18 req left), key#3 partially used locally. One dashboard turn ≈ 5-6 Gemini requests.

---

## APPENDIX — Cross-device chat history (2026-07-09, built)

**Decision (user-confirmed):** server-side history in a new **Postgres** container, **one shared
"team" pool** (no login; anyone opening the site sees all chats — accepted for the small client
team). A `user_key` column (default `'team'`) future-proofs per-user scoping without a migration.

**Backend:**
- `history-db` service in `docker-compose.yml`: `postgres:16-alpine`, volume `history_data`,
  published **loopback-only** (`127.0.0.1:5432`) for venv/psql dev; backend gets
  `HISTORY_DB_URL` injected (URL-safe password `HISTORY_DB_PASSWORD` in `.env`).
- `app/core/history.py`: SQLAlchemy-core store, ONE JSONB doc per thread (`chat_threads`),
  epoch-ms timestamps (round-trips frontend `Date.now()`), lazy engine + `create_all` on first
  use, portable update-then-insert upsert (tests run the same code on in-memory sqlite).
- `app/api/main.py`: `GET/PUT/DELETE /threads[/{id}]` — id charset-constrained, 5 MB/thread cap
  (413), whole-thread upsert, 503 when unconfigured/unreachable (frontend then falls back).
- `app/core/rate_limit.py`: refactored to `make_rate_limiter(scope, per_minute)`;
  `enforce_history_rate_limit` = separate `history:` bucket at 120/min so browsing history never
  eats the 20/min LLM budget (and vice versa). `enforce_rate_limit` unchanged in behaviour.
- New dep `psycopg2-binary==2.9.10` (installed in venv too).

**Frontend (`useGlowstarRuntime.js` + `api.js` + `chatStore.js`):**
- Mount: `GET /threads` (metadata only) → server mode; opening a chat lazy-fetches its messages;
  every turn does a debounced (600 ms) whole-thread `PUT`; delete calls `DELETE`.
- **One-time migration:** first load pushes existing localStorage threads to the server, then sets
  `glowstar.threads.migrated.v1` (so wiping server history can't resurrect them).
- **Fallback:** any listing failure → old per-browser localStorage behaviour, silently.
- Safety details: `send()` blocked while a thread's messages are loading (can't base a turn on an
  empty placeholder and save over real history); transient error banners never persist; deleting a
  thread cancels its pending debounced save; export rows trimmed to 1000/message on save (backend
  cap is 5 MB/thread).
- This SUPERSEDES the old "multi-tab last-write-wins / localStorage quota" flagged items in §5 for
  the primary path (last-write-wins still applies BETWEEN devices editing the same thread; fine).

**Known limits (accepted):** no live sync between open devices (refresh to see another device's
new chats); delete on one device doesn't push to an already-open other device; shared pool = no
privacy between staff (that's the chosen model).

**Tests:** `tests/test_history.py` (sqlite in-memory, covers store CRUD + endpoints + 413/422/503
paths + memory reconstruction). Suite now **25 pass / 1 skip**.

**AUDIT (2026-07-09, 155-agent adversarial workflow: 7 dims × 3-skeptic verify + completeness critic).**
49 raw findings → ~17 distinct after dedup. 3 HIGH-priority items FIXED this session (verified):
1. **"Bot forgets" (memory divergence).** Threads are durable in Postgres but LLM memory was Redis-only
   (24h TTL, 6 turns) → reopening an old/cross-device thread showed full history the model had no
   recollection of. FIX: `app/api/main.py::_load_history` — if the Redis session is empty, rebuild
   follow-up context from the durable thread messages (`sessions.history_from_messages`) and warm Redis.
   `DELETE /threads` now also `clear_session`s. Verified in-container: expired session → rebuilt from PG.
2. **X-Forwarded-For rate-limit bypass** (`app/core/rate_limit.py::_client_ip`). First XFF hop is
   client-controlled (nginx APPENDS the real peer), so a rotating fake header minted unlimited buckets →
   the 20/min (chat) + 120/min (history) caps were void with no auth. FIX: prefer nginx's `X-Real-IP`,
   else the LAST XFF hop. Proven: rotating spoof now collapses to one constant key. NOTE: this was a
   PRE-EXISTING weakness (the guest→IP keying predates the history feature; my refactor only inherited it).
3. **First turn lost in the mount-probe window** (`useGlowstarRuntime.js`). Before the async probe
   resolved, `serverModeRef` was null so a turn persisted nowhere, then `setThreads(list)` REPLACED state
   and dropped it. FIX: `mergeThreads` (never clobber a window-created chat) + flush-persist once mode is
   known + set mode BEFORE migration + only `markMigrated()` when EVERY push lands (also fixes the
   partial-migration-orphan medium finding).

**SECOND FIX BATCH (2026-07-09, "history hardening" — all verified, tests 32 pass / 1 skip):**
- **Silent data loss FIXED.** Server-mode save failures were swallowed with no backup, and a tab closing
  within the 600ms debounce lost the turn. Now `frontend/src/lib/chatStore.js` has an UNSYNCED backup
  (`glowstar.unsynced.v1`): a failed PUT stashes the thread locally; a `pagehide`/`visibilitychange`
  flush stashes threads still debouncing OR mid-PUT (via `inFlightRef`); mount reconciliation retries
  them and clears on success. A save confirmed on the server clears its backup.
- **Delete-undone-by-in-flight-PUT FIXED.** `deletedIdsRef` — a PUT that lands after a DELETE re-deletes
  the row; pending/backup entries for a deleted id are dropped.
- **Byte-accurate size cap** (`app/api/main.py` put_thread): measures UTF-8 BYTES incl. title, so
  multi-byte (Gujarati/emoji) can't store ~3× the 5 MB cap. Verified: 12 MB multibyte PUT → 413.
- **Thread-id collision FIXED** (`useGlowstarRuntime.js` `newThreadId`): `crypto.randomUUID()` instead of
  `Date.now()+rand(1e4)`, so two devices can't collide onto one id and merge two chats.
- **Redis-down → graceful** (`app/core/rate_limit.py`): the limiter FAILS OPEN on Redis errors (logged)
  instead of an unhandled 500. Verified: stopped redis → GET/PUT /threads still 200.
- New tests: `tests/test_rate_limit.py` (XFF anti-spoof, fail-open, 429, scope isolation — also covers the
  previously-untested default /chat limiter) + byte-cap + memory-reconstruction cases in test_history.py.

**THIRD FIX BATCH (2026-07-09, "tamper/growth protection" — verified, tests 37 pass / 1 skip):**
- **Soft-delete (recoverable).** `app/core/history.py`: DELETE now tombstones (`deleted_at` epoch-ms)
  instead of hard-deleting, so a delete in the no-auth shared pool isn't instantly destructive; list/get
  exclude tombstones. New `POST /threads/{id}/restore` undoes it within a 30-day window
  (`HISTORY_SOFT_DELETE_DAYS`). Old tombstones are opportunistically hard-purged on the next delete (no
  scheduler needed). Idempotent PG-only migration `_ensure_columns` adds the column to existing DBs on
  first use (verified live). NOTE: true per-user ownership still isn't enforceable without login — this
  makes deletes RECOVERABLE, which is the meaningful protection given the shared pool.
- **Thread-count cap.** `MAX_THREADS` (default 10000, `HISTORY_MAX_THREADS`) bounds a disk-fill DoS: a
  brand-NEW thread past the cap is refused with **507** (existing threads still save); the frontend then
  falls back to localStorage. Verified: PUT over cap → 507, update-at-cap → 200, soft-delete frees a slot.
- `restore_thread` endpoint has NO UI yet (an "undo delete" / admin-recover is the trivial follow-up).

Remaining audit items (NOT yet fixed, ranked): split-brain after a mid-life probe failure (migrated flag
sticks → fallback-mode threads never sync); cross-device concurrent same-thread PUT is last-write-wins;
nginx `/threads` inherits the 300s SSE timeout; no "undo delete" UI for the new restore endpoint. Full
deduped list + severities in the session summary + [[glowstar-history-audit]] memory.
