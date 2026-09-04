# GlowStar chatbot — engineering handoff

**Written 2026-09-03.** Everything a developer new to this project needs: what
it is, why answers go wrong, every known bug and its fix, and what to build
next.

> **Read §3 before writing any SQL against this database.** It is the
> difference between a correct answer and a confident wrong one.

---

## 1. What this is

A question-answering bot over **AasthaErp**, the ERP of a natural-diamond
manufacturer (factory in Surat, office at BDB Mumbai CC-7070). Staff ask in
English or Gujlish — *"aa mahine ketla nang thaya?"* — and get an answer from
their own live data.

| | |
|---|---|
| Backend | FastAPI, Python 3.12, SQLAlchemy + pyodbc |
| Database | SQL Server 2022, **read-only** login `glowstar_ro` |
| Frontend | static SPA on `:8080` |
| Stack | Docker Compose — backend, frontend, redis, postgres (chat history) |
| Models | provider-agnostic; Gemini / Groq / NVIDIA / OpenRouter / local |

### Run it

```bash
# tests (needs the DB reachable; ~90s)
PYTHONPATH=. ./venv/Scripts/python.exe -m pytest tests/ -q

# the stack — ALWAYS pass -p, or compose invents a second project
docker compose -p glowstar_chatbot up -d --build backend
```

```bash
# END-TO-END DEMO CHECK - run this before any client meeting.
# Hits the live API through nginx exactly as the browser does, and diffs every
# answer against a direct query. 15 questions, all covered families.
PYTHONPATH=. ./venv/Scripts/python.exe -m scripts.demo_check
```

**The single most common mistake:** editing a file and testing the container
without rebuilding. Code lives in the image, not a bind mount. A one-day-stale
container is exactly how the pending-certification bug reached the client — see
§4.1.

---

## 2. Architecture — and why it is shaped this way

A question passes through five layers. **Each one can answer or refuse before
the model is ever called**, and that is deliberate: every deterministic answer
is one the model cannot get wrong.

```
question
   ↓
1. GATES            access_guard · date_gate · lab_gate · smalltalk_gate
   ↓                (refuse, or ask a clarifying question, pre-LLM)
2. RECIPE ROUTER    recipe_router.match() → a recipe + resolved parameters
   ↓                (answers with NO model call at all)
3. QUERY RULES      query_rules.violations() — rejects known-wrong SQL
   ↓
4. THE MODEL        writes SQL with tools · sees the schema + fired rules
   ↓
5. POSTPROCESS      facts.py totals · count_guard · scope banners · export
```

### The central idea: recipes

A **recipe** is a Python function that owns one question family and writes the
SQL itself. The model's only job becomes *pick the recipe, fill in the kapan /
department / dates*.

This matters because **every wrong answer this project has produced came from
the model writing SQL freely.** Where a recipe exists, the answer reproduces
the client's own ERP screens figure-for-figure. Encoding a business rule once,
in code, beats explaining it to a model on every question.

| Recipe | Answers | Where |
|---|---|---|
| `lab_results_report` | GIA/HRD/IGI results, PLS-vs-GIA | `reports.py` |
| `pending_lab_report` | polished, not yet sent to a lab | `reports.py` |
| `cut_purity_report` | MFG grade vs lab grade | `reports.py` |
| `department_report` | one department over a period | `reports.py` |
| `plan_rows_report` | plans created by a department | `reports.py` |
| `stage_gap_report` | "has X plan, no Y plan yet" | `reports.py` |
| `employee_report` | one worker's plans and damage | `reports.py` |
| `kapan_report` | the whole picture for one kapan | `reports.py` |
| `production_report` | production over a period, on a named basis | `reports.py` |
| `quick_facts` | one-line counts and live snapshots | `quick_facts.py` |

### Cost discipline — read before adding a tool

`TOOL_SPECS` is **re-sent to the model on every round**, and a question costs
several rounds. Two extra specs measured **+680 tokens/round** and blew the
budget outright.

- Groq's free tier **hard-refuses** anything over 8,000 tokens/minute
- `tests/test_prompt_budget.py` enforces a ceiling; it has been raised twice
  already and says **do not raise it a third time**
- **So: new recipes are matched in `recipe_router` and dispatched through
  `TOOL_HANDLERS`, with NO `TOOL_SPECS` entry.** They then cost nothing until
  used. `cut_purity_change`, `plan_rows`, `stage_gap` and `employee_report` all
  work this way.

---

## 3. The data model — every trap, and the correct reading

**This section is the product.** Each line below was a wrong answer once.

### 3.1 The stage ladder

Everything hangs off `tblPlanMaster.RapVer`:

```
RST → CLV → ADM → MKB → MFG → PLS → GIA / HRD / IGI
 │     │     │     │     │     │      └─ the certifying lab
 │     │     │     │     │     └─ in-house grade ("polish planned", "assorted")
 │     │     │     │     └─ the MAKER — who manufactured it
 │     │     │     └─ marking checkpoint
 │     │     └─ admin check
 │     └─ marking (Marker-1..4 work here)
 └─ rough estimation
```

Every figure the client's own procedures compute carries
**`IsDamagePlan = 0` AND `IsApproved = 1`**. Read their SQL before inventing a
rule — it ships inside the backup:

```sql
SELECT o.name, m.definition FROM sys.objects o
JOIN sys.sql_modules m ON o.object_id = m.object_id
WHERE m.definition LIKE '%<the thing you care about>%';
-- GetPLSSUM, GetMFGSUMBYLAB, sp_GetKapanPerformance ...
```

### 3.2 Traps that cause wrong numbers

| Trap | Wrong | Correct |
|---|---|---|
| **"Pending" is positional** | `has PLS, no GIA` → **12** | the packet's LATEST approved row IS the PLS row → **2** |
| **Sibling plans** | dedupe to newest CLV row → **1** | one rough is planned into SEVERAL stones; keep them all → **2** |
| **Plan vs packet attributes** | `tblPacket.Purity` / `.CurrentWt` | `tblPlanMaster.Purity` / `.PolishedWt` — **1 vs 4 packets** |
| **`CurrentWt` on an uncut kapan** | reported as "size" | it is the **ROUGH** weight; `PolishedWt` is NULL until polished |
| **Weight on live snapshots** | `SUM(PolishedWt)` → 1.001 ct for 1,073 stones | `CurrentWt` — populated on 100% |
| **Hold is kapan-level** | `tblPacket.IsOnHold` → **2 rows in the whole table** | `JOIN tblKapan WHERE k.IsOnHold = 1` → **11,967 packets** |
| **Jangad** | `tblJangad` (movement register) → 16× over | `tblJangadPackets WHERE ISNULL(IsReceived,0)=0` |
| **`IsVerified`** | 14 rows in the entire DB | `IsApproved` |
| **Repairs** | `tblRepairLogNew` — 46× inflated | `tblRepairCommentVision` only (starts 2025-04-08) |
| **Rate cards** | `SUM(tblLabourRate.Amount)` — 16.6× | money paid is `tblPointRateLabour` |
| **`tblKapanValue`** | SUM it → 77× | it is a DAILY SNAPSHOT; totals come from `tblKapan` |
| **Date ranges** | `BETWEEN '2026-07-01' AND '2026-07-31'` | `>= start AND < next_start` — `smalldatetime` drops the last day |
| **Shape families** | `Shape = 'OV'` — 40% of ovals | `IN ('OV','F.OV','S.OV','OVM')` |
| **Employee name** | GROUP BY name | 15 rows share one name — **carry `tblEmployee.Code`** |
| **Employee code** | assumed unique | B146, M2128, M2D003 each map to **2 people** — list, don't pick |
| **`ROLLUP` / `CUBE`** | subtotal rows inflate the total | plain `GROUP BY` |
| **Attendance** | any table | **not answerable** — feed died 2025-04-05, `EmpId` NULL on all rows |

### 3.3 Spellings that are wrong in the schema — and must stay wrong

`Purity` **is** clarity (there is no clarity column) · `Florecent` on
`tblPacket` but `Florocent` on `tblFinalPacket` · `Grede` · `IsIssed` ·
`IsRecyleble` · `WightLoss` · `tblEmployeeTimeAttandance`

### 3.4 Ambiguous by nature — say which basis you used

- **Production** — `tblFinalPacket` (finished) vs MFG stage (maker) differ by
  up to 14% in a month. Name the basis.
- **Stock** — `RunningProcess = 'IN Stock'` is ~90% of every packet ever
  created, so it cannot mean "right now". Unresolved; offer both readings.
- **Kapan pieces** — packet rows / `SUM(Pcs)` / finished rows all differ.

### 3.5 Y-codes are not people

`Y111`, `Y126`, `Y137`… are **Fency job-work vendor firms** (MAHADEV JEMS,
TRITH DIAMOND). Never rank them beside individual karigars. Never `INNER JOIN`
to `tblEmployee` to prettify a name — that is how they vanish.

---

## 4. Every bug found, and its fix

### 4.1 Stale container shipped a known-wrong answer — **FIXED**
Pending certification returned **12**; the truth is **2**. The correct
definition was already in `reports.py`. The running container was built from an
image one day older. **Always `--build`.**

### 4.2 Anti-join instead of positional pending — **FIXED**
`has PLS, no GIA` also counts stones that moved on — ten of the twelve had
been certified at **HRD**. Enforced by the `stage_pending` rule.

### 4.3 Plan attributes read off the packet — **FIXED**
`p.Purity` / `p.CurrentWt` instead of the plan row gave **1 packet against 4**,
and the sets barely overlapped. New rule `plan_attributes_from_the_plan_row`.
Its first draft only fired on "marker &lt;n&gt;", missing Blocking, Sarin,
Dilate — **12 of 18** combinations leaked. Trigger now matches the question
*shape*, not the department name.

### 4.4 Guard rejected a correct query, so the bot refused — **FIXED**
`lab_results` required `COUNT(DISTINCT Packet_ID)`. A per-packet **listing**
cannot contain one, so the guard rejected it and the model refused outright.
Now exempt when the query has no aggregate at all. *A false rejection is worse
than the bug — it makes the bot look incapable of something it can do.*

### 4.5 Date picker on a kapan question — **FIXED**
`_REPORT_RE` matches the bare word `gia`; with no month in the question the
gate demanded a date range for a kapan-scoped question. A kapan is a parcel of
rough, not a period. `date_gate.names_a_kapan()` now resolves against the
**live `tblKapan` list** — no name-shape guessing.

### 4.6 One missing word in a routing regex — **FIXED**
"cut **and** clarity" routed to the verified recipe; "cut **or** clarity" did
not, and free SQL returned **337 rows against a true 288** — counting damage
plans, superseded rows, and 26 stones certified at HRD.

### 4.7 The model recited a number instead of querying — **FIXED**
The directive said *"IsVerified is set on **14 rows**"*, and the bot answered
**14** to "how many planning verified this year". Twice, on 2026-09-03. The
guard test only caught comma-thousands, so bare `14` was invisible. Widened —
which immediately exposed **five more** rules handing over recitable figures,
including `kapan_pieces_points`, which contained the literal answer to a real
question. **Never put a figure in a directive.** Comments and rejection
messages are safe; the model sees neither before it queries.

### 4.8 47 kapans could never be named — **FIXED**
31 real kapan names are English stopwords (`AA`, `GO`, `IN`, `IS`, `IT`, `ME`,
`NO`, `ON`, `OR`, `TO`, `US`, `VS`…) and 16 use the `21WD` shape the token
pattern could not see. The stopword list still applies to a bare token but is
lifted when the user says **"kapan &lt;name&gt;"**. Two traps closed on the way:
the mirror form made *"…**of** kapan AA"* resolve to the kapan named **OF**,
and *"kapan **ma**"* (Gujarati for *in the kapan*) resolved to the kapan
**MA**. Now one-directional, with Gujarati postpositions excluded.
**47 → 5**; the remaining five (`MA NA NI NO NU`) are genuinely ambiguous and
correctly decline.

### 4.9 A decimal changed the department — **FIXED**
`0.80` split into tokens `0` and `80`, and the window `"0 80 marker"`
fuzzy-matched the department literally named **Marker** — the question asked
for **Marker-2**. Different people, wrong answer, no error. Decimals are now
stripped first, and an **exact** match beats a fuzzy one regardless of window
length.

### 4.10 `Open` is a reserved word — **FIXED**
A fact aliased a column to `Open`, the query failed, the error was swallowed
and the answer rendered **blank** — worse than an error, because it looks like
an answer.

### 4.11 A weight off by 400× — **FIXED**
Memo reported **1.001 ct for 1,073 stones**: `PolishedWt` is NULL on 1,072 of
them. `CurrentWt` gives 415.854 ct, which matches the jangad total, as it must
— they are the same goods-out state. That agreement is now a test.

### 4.12 The grade report was GIA-only — **FIXED**
175 packets are graded at HRD and 6 at IGI; "MFG vs HRD" matched no recipe and
fell to free SQL. The lab is now a parameter.

### 4.13 `docs/` was never actually git-ignored — **FIXED**
`.gitignore` carried a comment saying *"The whole folder is ignored"* and
**nothing implemented it** — `git check-ignore docs/HANDOFF.md` matched
nothing, and the `!README.md` negations were dangling with no ignore to negate.
A plain `git add .` would have committed the whole folder: the same client
material that had to be purged from history on 2026-08-05. Found while writing
this document.

### 4.14 `kapan_report` died twice on its first run — **FIXED**
Two runtime traps worth knowing before writing any recipe SQL:
`Weight` is **ambiguous** (both `tblJunk` and `tblKapan` have one) so an
unqualified reference throws *Ambiguous column name*; and **`sql_guard`
rejects `--` comments inside a query outright**, so explanatory notes must live
in Python, never in the SQL string.

### 4.15 `scripts/coverage.py` crashed on Gujlish — **FIXED**
An unhandled `UnicodeEncodeError` on the Windows console codepage killed the
whole report mid-print. Never let formatting kill a measurement.

### 4.16 The gates accepted periods the router could not resolve — **FIXED**
`date_gate._PERIOD_RE` recognised **"today"**, **"yesterday"** and a **bare
year**, so the picker stayed quiet — but `resolve_period` could not turn any of
them into dates, so `match()` declined and the question fell to free SQL.
*A period one layer accepts must be one the next layer can resolve*, or the two
disagree silently. Also: the router's `_REPORT_RE` does not contain the word
"production", so **"Fency department production for June 2026"** matched
nothing at all.

### 4.17 Developer notes were shown to the client verbatim — **FIXED**
A `quick_fact` renders with **no model in the loop**, so its note goes straight
to the screen. The first versions read *"tblPacket.IsOnHold is set on two rows
in the whole table and must never be counted"* — written for the model, shown
to a customer. Rewritten in business language; the reasoning lives in source
comments. **Rule: anything a recipe returns as text is client-facing.** Tests
now pin the SQL that is read, not the wording, so the prose can keep improving.

### 4.18 `"across all 1 row"` under a two-packet figure — **FIXED**
Every recipe Summary is a single aggregate row, so the count said nothing —
except to a client, to whom it said the answer rests on one record.

---

## 5. The demo set — verified end to end on 2026-09-03

All fifteen answer via recipe, in **0 ms, with no model call** — so rehearsing
burns no Gemini quota. `scripts/demo_check.py` re-verifies them against the
live API and a direct query.

| Family | Example question |
|---|---|
| Live counts | how many kapans / packets on jangad / on memo / on hold / employees |
| Pending certification | polished GIA pending for MFG-1 for July 2026 |
| Grade comparison | NS26 — MFG grade vs GIA grade on cut or clarity |
| Stage gap | NS26 — approved CLV plan but no approved PLS plan, IF–VS2, 0.5–1.0 ct |
| Plans by department | QA26 — planned by Marker-2, FL–VVS2, 0.3–0.8 ct |
| Kapan report | full packet report for kapan NS26 |
| Employee report | report of employee M4117 for June 2026 |
| Production | daily production 1–30 Jun 2026 · packets made in June 2026 |
| Lab results | GIA results for May 2026 |
| Department report | department MFG - 1 for July 2026 |

**Anything outside these families goes to free SQL.** In a meeting: *"let me
take that and come back with a verified answer."*

## 6. Still open

| Item | Detail |
|---|---|
| **The 201** | The client's screen shows **201** for MFG-1 pending certification. We compute **2** and can prove it; the old anti-join gave 12. Neither explains 201. **Needs their export or a few packet numbers through `scripts/packet_trace.py`.** This is the only item where we do not know whether we are right. |
| **7 cold cases get the date picker** | JP-1, JP-3, DRS-3, EDA-3, CT-02, CT-08, CT-09 have verified answers containing **no date at all**. Pinned by `test_date_picker.py`; whether "party wise jangad" should default to all-time is a **product decision**. |
| **5 unreachable kapans** | `MA NA NI NO NU` — ambiguous with Gujarati postpositions. Declining is correct. |
| **5 directives still carry figures** | `repairs`, `attendance`, `bonus_earnings`, `junk`, `kapan_value_snapshot` — on the explicit exemption list as *contrast* figures. Clear them if you can. |
| **Provider economics** | Gemini free tier = 20 requests/day against 449 served; 28% failure; 30–48s. Needs a paid tier. |
| **Unqualified column predicates** | `FROM tblPacket WHERE Purity = 'VS1'` (no alias) is not attributed to a table by the plan-attribute guard. A miss, not a false rejection. |

---

## 7. Coverage — the number that decides the product

Measured over **206 unique real questions** from the production log:

| Path | Session start | Now |
|---|---:|---:|
| **Deterministic recipe** | 29% | **45%** |
| Asks a clarifying question first | 21% | 19% |
| **Free SQL — where every wrong answer lives** | **49%** | **35%** |

Weighted by how often each question is actually **asked** (435 log entries
rather than 206 distinct), recipes cover **58%** of real traffic — the
common questions are the ones already covered. Quote the distinct figure
internally and the weighted one to the client; say which you mean.

```bash
# re-measure any time - reads the container log by default
PYTHONPATH=. ./venv/Scripts/python.exe -m scripts.coverage
```

**This is the metric to track.** Not model size, not test count. Every wrong
answer this project has produced came from the free-SQL slice; shrinking it is
the whole job.

### What is left, by cluster

| Recipe to build | Questions | Notes |
|---|---:|---|
| Damage report | ~5 | **needs the client to confirm the definition** |
| Dimension breakdown | ~4 | by colour / shape / cut — must roll up shape families |
| Bonus / incentive / labour | ~4 | **`access_guard` refuses pay questions** — check before building |
| Analytics overview | ~5 | composite; lowest priority |

~15 of the remaining questions are **not recipe targets** — docker commands, a
leaked API key, "write me a poem", conversational fragments ("last month",
"yes do that"). **~80% is the honest ceiling.**

---

## 8. How to add a recipe

1. **Establish the truth by hand.** Query the DB, get the right answer, find
   the traps. *This is the slow part and it is the part that matters.*
2. **Write the SQL** in `reports.py` with the traps encoded, and a comment
   saying what each one cost.
3. **Write the report function** — resolve scope (kapan/department/employee),
   run, format, state the caveats in the returned text.
4. **Wire the route** in `recipe_router.py` — `match()` for the question,
   `answer()` for the dispatch and lead-in, plus a `TOOL_HANDLERS` entry.
   **No `TOOL_SPECS` entry** (§2).
5. **Write tests** pinning the verified figures *and* the properties. Prefer
   **invariants** over snapshots — see below.
6. **Run the full suite, check the prompt budget, rebuild the container.**

### Rules that are not negotiable

- **Never hardcode a figure the query can compute.** Row counts move on every
  restore. `date_gate` asks `tblKapan` what a kapan is; it does not pattern-match
  names.
- **Test invariants, not snapshots.** `assert NS26 == 288` proves nothing and
  breaks on restore. Assert instead: no damage plans, no null-GIA rows, no
  duplicate packets, the MFG row is the latest. Those are checkable for **any**
  kapan — and verify your test *fails* on the wrong answer, or it is worthless.
- **A false rejection is worse than a miss.** A rejected correct query costs a
  working answer. `test_answer_integrity_fixes.py` asserts zero rejections
  across the cold-case ground truths — keep it at exactly `["CT-04"]`.
- **Never put a figure in a directive** (§4.7).
- **Ambiguity means ask, never guess.** `OS26`/`OR26` and `NI26`/`NS26` both
  exist and are different stones. We have queried the wrong kapan twice.
- **Watch out for backslashes in `query_rules.py`.** A literal `\b` in that
  file has twice become a `0x08` BACKSPACE byte, silently killing every word
  boundary. Write patterns with **no backslashes** — `[.]`, `[0-9]`, `[ ]*`,
  `(?<![a-z])` — and assert `chr(8) not in pattern`.

---

## 9. Operations

### Database refresh
Backups live in `C:\SQLBackups`. Rename the current `AasthaErp_new` →
`AasthaErp_<mmdd>`, restore the new one **as `AasthaErp_new`** so no config
changes. Logical file names are `JogiErp` / `JogiErp_log`, never `AasthaErp`.

> **The physical filenames end up CROSSED.** The rollback keeps the original
> files, so the OLD database lives in `AasthaErp_new.mdf` and the LIVE one in
> `AasthaErp_new_0821.mdf`. **Never delete a database by its `.mdf` name** —
> always `DROP DATABASE <name>`.

A `.bak` **moved** into `C:\SQLBackups` keeps its old ACL (NTFS does not
re-inherit on a same-volume move) → *Operating system error 5*. Fix with
`icacls <file> /reset`.

**After every restore:** run `tests/test_prompt_freshness.py`, re-verify
`test_cut_purity_change.py` (the ERP-matched figures), and rebuild
`docs/DATABASE_MAP.md`.

### Logs
The container writes to a **Docker volume**, not the host `logs/`. The host
directory is written by local test runs — do not diagnose production from it.

```bash
docker exec glowstar_chatbot-backend-1 sh -c "grep -h 'WARNING\|ERROR' /app/logs/agent.log | tail -40"
```

Watch for: `WRONG-SOURCE` (guard rejected the model's SQL) ·
`COUNT-MISMATCH` (the prose disagrees with the data — **this is how §4.7 was
found**) · `NO-QUERY TURN` (nothing ran) · `PENDING-VIA-RECIPE`.

### Data currency
The backup ends **2026-08-21**. `tblPointRateLabour` (bonus/labour) is posted
**in arrears** and only reaches 2026-08-05 — recent weeks are incomplete, not a
downturn.

---

## 10. Prompt 
> You are working on the GlowStar chatbot — a question-answering bot over
> **AasthaErp**, a diamond manufacturer's SQL Server ERP.
>
> **Read `docs/HANDOFF.md` §3 before writing any SQL.** That database is full
> of traps that produce confident wrong answers: "pending" is positional not an
> anti-join; `Purity` means clarity; `CurrentWt` is the rough weight on an
> uncut kapan; hold is kapan-level because `tblPacket.IsOnHold` is set on two
> rows in the entire table; one rough packet is planned into several stones so
> plan rows are siblings, not supersessions; employee names AND codes are both
> non-unique.
>
> **The architecture exists because the model writing SQL freely is what
> produces wrong answers.** Every wrong answer this project has shipped came
> from that path. The fix is always the same: work out the truth once, by hand,
> against the live database, then freeze it into a **recipe** — a Python
> function that owns one question family and writes the SQL itself.
>
> **Working rules:**
> - Verify against the live database. Never trust a remembered figure — even
>   the ones in this document may have moved since it was written.
> - Never hardcode what the query can compute.
> - Test invariants, not snapshots, and check your test fails on the wrong
>   answer.
> - A false rejection is worse than a miss.
> - Ambiguity means ask, never guess — `OS26` and `OR26` are different stones.
> - New recipes are router-matched, **never** added to `TOOL_SPECS` — the
>   prompt budget has no room.
> - Rebuild the container after every change:
>   `docker compose -p glowstar_chatbot up -d --build backend`
> - Run the full suite before saying anything is done.
>
> **The metric is coverage** — the share of real questions answered by a recipe
> rather than free SQL. It is 45% of distinct questions and 58% of real
> traffic today. Raising it is the job.
>
> When you fix something, say what it cost in the comment: *"this returned 337
> against a true 288"*. Six months from now that sentence is the only thing
> stopping someone reverting it.

---

## 11. Reference

| Path | What |
|---|---|
| `app/agent/reports.py` | all recipes |
| `app/agent/quick_facts.py` | one-line facts and live snapshots |
| `app/agent/recipe_router.py` | question → recipe + parameters |
| `app/agent/query_rules.py` | 30 rules that reject known-wrong SQL |
| `app/agent/date_gate.py` · `access_guard.py` · `lab_gate.py` | pre-LLM gates |
| `app/agent/facts.py` | deterministic totals under every answer |
| `app/schema/` | live schema extraction, glossary, router |
| `docs/DATABASE_MAP.md` | tables, freshness, decoys — **rebuild after restore** |
| `scripts/demo_check.py` | **end-to-end check through the live API — run before every meeting** |
| `scripts/coverage.py` | the coverage metric over the real question log |
| `scripts/packet_trace.py` | trace one packet through every stage |
| `scripts/cold_cases.py` | 40 ground-truth question/SQL pairs |
| `tests/test_cut_purity_change.py` | the ERP-verified figures — **do not soften** |

### Verified figures (as of the 2026-08-21 backup)

| Question | Answer | Status |
|---|---|---|
| NI26 cut / purity changes | **8 / 18** | matches the client's screenshot, twice |
| May 2026 lab results | **2,562 packets** | matches their ERP |
| MFG-1 GIA pending, July | **2 packets** | matches the client — *their screen says 201, unresolved* |
| NS26 MFG vs GIA | 288 packets / 298 rows | verified by hand |
| Active employees | 369 | `IsActive = 1` |

**These move after a restore. Re-verify; do not trust this table.**
