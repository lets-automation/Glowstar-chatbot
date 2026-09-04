# AasthaErp — database map

Built 24 Aug 2026 against the **2026-08-21** backup (`AasthaErp_new`, data ends
2026-08-21 ~13:02). **Rebuild this after every restore** — row counts and, far
more importantly, *feed end dates* move.

Scope: 264 tables, 191 with data, 73 empty, 27,436,599 rows. Only **51 foreign
keys** are declared, so joins are inferred from naming — a large part of why
free-form table choice goes wrong.

## How to read this

Three labels, not interchangeable:

- **ERP-VERIFIED** — reproduced figure-for-figure against a screenshot of the
  client's own ERP screen. Only the lab report has earned this.
- **MEASURED** — computed from the database and internally consistent, but never
  checked against what the client's ERP shows for the same question.
- **UNVERIFIED** — a plausible reading of the schema. Do not put these in front
  of the client without checking first.

---

## 1. Freshness — which feeds are alive

The most decision-relevant section here. A dead feed returns 0 for any recent
period, and 0 reads as "no activity" when it really means "this feed stopped".

### LIVE to the backup cutoff

| Table | Rows | Date column | Newest |
|---|---:|---|---|
| `tblPacketHistory` | 5,847,368 | ReciveTime | 2026-08-21 |
| `tblPacketIssue` | 5,847,227 | IssueTime | 2026-08-21 |
| `tblPlanMaster` | 1,316,677 | CreatDate | 2026-08-21 |
| `tblPlanMasterOptional` | 728,830 | CreatDate | 2026-08-21 |
| `tblIncentiveAmount` | 611,727 | TransactTime | 2026-08-21 |
| `tblRepairLogNew` | 584,031 | CreatedDate | 2026-08-21 |
| `tblPacketPoint` | 249,213 | ProcessDate | 2026-08-21 |
| `tblIssuedPacketDetail` | 228,677 | CreatedDate | 2026-08-21 |
| `tblJunk` | 215,158 | CreateDate | 2026-08-21 |
| `tblPacket` | 172,233 | ProcessStartTime | 2026-08-21 |
| `tblAllowMKBPermission` | 125,822 | CreateDate | 2026-08-21 |
| `tblAllowMrkAdminPermission` | 115,993 | CreatedDate | 2026-08-21 |
| `tblPlanReport` | 104,603 | CreatedDate | 2026-08-21 |
| `tblAllowMFGPermission` | 35,092 | CreateDate | 2026-08-21 |
| `tblJangad` | 17,220 | JangadDate | 2026-08-21 |
| `tblRepairCommentVision` | 4,471 | CreatDate | 2026-08-21 |
| `tblGraderRemark` | 4,400 | CreatedDate | 2026-08-21 |
| `tblIssuedPacket` | 1,600 | EntryDate | 2026-08-21 |
| `tblFinalPacket` | 179,990 | CreateDate | 2026-08-20 |
| `tblNcGroupAssigned` | 6,780 | CreatedDate | 2026-08-20 |
| `tblKapan` | 865 | DbUpdateStopDate | 2026-08-20 |
| `tblKapanChallan` | 849 | UpdateDate | 2026-08-20 |
| `tblLeaveReport` | 20,293 | LeaveDate_To | 2026-08-22 |

### LAGGING — a current-period question here understates

| Table | Rows | Date column | Newest |
|---|---:|---|---|
| `tblPointRateLabour` | 928,063 | ProcessDate | 2026-08-05 |
| `tblLabourResultEdit` | 5,456 | CreateDate | 2026-08-05 |
| `tblGPSLabour` | 525 | CreateDate | 2026-08-06 |
| `tblNcGroupConfig` | 926 | CreatedDate | 2026-07-31 |
| `tblPointRate` | 8,040 | CreatedDate | 2026-06-05 |

`tblPointRateLabour` is the one that matters: bonus/labour is posted **in
arrears**. The most recent weeks are INCOMPLETE, not a downturn. The prompt now
reads this end date live via `{FEED_END:tblPointRateLabour.ProcessDate}` instead
of naming a date that rots — see §7.

### DEAD — stopped long ago. These are the traps.

| Table | Rows | Date column | Newest |
|---|---:|---|---|
| `tblTimeAttendance` | 393,882 | Time | 2025-04-05 |
| `tblPlanReport_BKP` | 2,712 | CreatedDate | 2025-02-19 |
| `tblPacket_BKP` | 71,715 | CreateDate | 2025-02-10 |
| `tblLabourResultGIA` | 121,337 | ProcessDate | 2024-05-02 |
| `tblLabourResult` | 623,404 | ProcessDate | 2023-04-12 |
| `tblLabourResult_Compare` | 95,732 | ProcessDate | 2022-10-19 |
| `tblPacketPointGIA` | 75,712 | ProcessDate | 2022-09-30 |
| `tblCompanySchedule` | 8,212 | FromDate | 2022-06-30 |
| `tblStockIssue` | 15,947 | IssueDate | 2022-03-09 |
| `tblRepairLog` | 657,023 | Time | 2022-02-19 |
| `tblEmployeeCount` | 524 | Date | 2021-07-23 |
| `tblPlanMaster_Update` | 22,307 | UpdateDate | 2021-07-23 |
| `tblTimeAttendance_Demo` | 45,636 | Time | 2021-01-20 |
| `tblKtdPacket` | 728 | CreDate | 2019-12-09 |
| `tblEmpGIABonus` | 17,304 | GIADate | 2019-10-14 |
| `tblPacketPrint` | 31,858 | UpdatedOn | 2019-10-04 |
| `tblPacketDetail` | 179,163 | SendDate | 2017-09-25 |
| `tblEmployeeTimeAttandance` | 2,973 | OutTime | 2017-09-06 |

---

## 2. Decoys — the name matches the question, the content does not

| Question | The table you'd reach for | What it actually gives | Use instead |
|---|---|---|---|
| repairs | `tblRepairLogNew` (584k) | generic CRUD audit trail — **150,706** for 2025 | `tblRepairCommentVision` — **3,302** (46× inflation), starts 2025-04-08 |
| repairs | `tblRepairLog` (657k) | UI click log, dead since 2022 | as above |
| "planning verified" | `tblPlanMaster.IsVerified` | **14 rows in the entire database** | `IsApproved` — 31,317 packets in 2026 |
| headcount | `tblEmployeeCount` | dead 2021, last value 420 | `tblEmployee.IsActive = 1` — **369** |
| attendance | `tblTimeAttendance` | dead 2025-04-05, `EmpId` NULL on all 393,882 rows | nothing — **not answerable**, say so |
| lab results | `tblFinalPacket.Lab` | finished stones by certifying lab — 3,227 for May | `tblPlanMaster` RapVer IN ('GIA','HRD','IGI') — **2,562** |
| issued packets | `tblIssuedPacket` (1,600) | header only | `tblIssuedPacketDetail` (228,677) |

Every decoy above that can be written as a SQL constraint is now **enforced** in
`app/agent/query_rules.py`, not merely documented.

---

## 3. Question → table

| Question family | Source | July 2026 | Confidence |
|---|---|---:|---|
| Lab / GIA / HRD / IGI results | `lab_results` **tool** → `tblPlanMaster` RapVer IN ('GIA','HRD','IGI'), period on `CreatDate`, `COUNT(DISTINCT Packet_ID)` | 3,692 | **ERP-VERIFIED** (May = 2,562) |
| Production / finished output | `tblFinalPacket.CreateDate` | 4,476 | MEASURED |
| Production by maker / department | `tblPlanMaster` RapVer='MFG' + `EmpId` → `tblEmployee` | 4,555 | MEASURED |
| Department report (all sections) | `department_report` **tool** | — | MEASURED |
| Planning approved / "verified" | `tblPlanMaster.IsApproved = 1` (+ `ApproveDate`) | 31,317 (2026) | MEASURED |
| Damage | `tblPlanReport.IsDamageReport = 1` | 179 | MEASURED |
| Repairs | `tblRepairCommentVision` only | 41 | MEASURED |
| Junk / scrap | `tblJunk.CreateDate` | 7,391 | MEASURED |
| Bonus / labour by employee | `tblPointRateLabour.ProcessDate` (ARREARS) | 25,619 | MEASURED |
| Incentive | `tblIncentiveAmount.TransactTime` | 3,306 | MEASURED |
| Packets out on jangad now | `tblJangadPackets` WHERE `IsReceived = 0` | 1,072 (81 open jangads) | MEASURED |
| Stones out on memo now | `tblPacket.IsOnMemo = 1` | 1,073 | MEASURED |
| Diamonds on hold now | `tblPacket.IsOnHold = 1` | 2 | MEASURED |
| Active workforce | `tblEmployee.IsActive = 1` | 369 | MEASURED |
| Attendance | none — feed dead since 2025-04-05 | — | **not answerable** |

`tblJangad.TransType` is `Issue` (8,668) / `Receive` (8,551).

### Who made a stone (employee attribution) — cross-validated

The maker is the `EmpId` on the **latest** `tblPlanMaster RapVer='MFG'` row for
the packet. Measured for July 2026 across the 3,692 lab-stage packets:

- resolves to a named employee on **100%** — no coverage loss
- cross-checks at **99.40%** against the wholly independent `tblPacket.MFGEmpId`
  column, with identical totals (3,692) and an identical Fency figure (1,643)
- the ~0.6% that disagree are packets **re-issued to a different maker after
  grading**: the plan row holds the maker *at the time*, `tblPacket.MFGEmpId`
  holds the *current* one. The plan row is right for "who made the stones we
  graded in July".

`lab_results` therefore takes a `department` argument and adds a by-employee
table — this is the most-asked question in the logs (55×). Note that Fency's
"employees" are **outside vendor firms** (MAHADEV JEMS, SHREE SIDDHI VINAYAK
DIAMOND…), not individual karigars.

Department spelling is matched for the caller: exact → squashed
(`mfg-1` → `MFG - 1`) → substring → a single close match at 0.8 similarity
(`fancy` → `Fency`, which the client types in their own logs). Two plausible
matches stay a question rather than a guess, and all 83 real department names
round-trip to themselves.

### PRODUCTION IS AMBIGUOUS — needs the client

Two defensible definitions that do **not** agree:

| Period | A: `tblFinalPacket` (finished) | B: MFG stage (maker) | Divergence |
|---|---:|---:|---:|
| May 2026 | 3,227 | 2,783 | **−13.8%** |
| Jun 2026 | 4,007 | 4,001 | −0.1% |
| Jul 2026 | 4,476 | 4,555 | +1.8% |

Only 3,358 packets appear in **both** July sets, so about a quarter of each is
missing from the other — they count different *events*, not the same thing twice.
Until the client's production screen settles it, the `production_basis` rule does
not force a table; it forces the answer to **say which basis it used**. An
unlabelled number that moves 14% between two reasonable readings is exactly how
trust was lost.

Damage has two paths that nearly agree: `tblPlanReport.IsDamageReport`
(133 / 159 / 179 for May–Jul) vs `tblPlanMaster.IsDamagePlan` (137 / 157 / 175).
The report register is the better source; the small gap is unexplained.

**Still UNVERIFIED — do not demo without checking:** "in stock".
`RunningProcess = 'IN Stock'` covers 155,841 of the 172,233 packets ever created,
which cannot mean "in stock right now"; 16,924 packets have no `tblFinalPacket`
row (not finished). Ask the client which figure their stock screen shows.

---

## 4. Dimensions that must be normalised before grouping

- **Shape** — fancy/special variants are separate values. Oval = `OV` 3,265 +
  `F.OV` 4,866 + `S.OV` 75 + `OVM` 1. `Shape='OV'` under-reports by more than
  half, and F.OV *outnumbers* plain OV. Same pattern for PS and MQ.
- **Department** — `'MFG - 1'` has spaces (343 people) while its siblings are
  `'MFG-2'` (362), `'MFG-4'` (205). Also `'VL MFG-1'` (115), `'MFG-1 CHECKER'`,
  `'MFG Admin'`. Match on `REPLACE(DepartMentName,' ','')` and list back what
  matched.
- **`tblJangad.Process`** is free text — double spaces, vendor names, misspellings.

---

## 5. New in the 2026-08-21 backup: match pair

Four new tables, plus five new `tblPlanMaster` columns (`IsMatchPair`,
`MatchPairId`, `Length`, `Width`, `OrderDetailId`).

- `tblMatchPairCriteria` (664 rows) — a catalogue of candidate certified stones,
  **one row per stone, NOT per pair** (StoneNo, Lab, ReportNo, full 4Cs,
  measurements, KeyToSymbols).
- `tblMatchPairTolerance` (1 row) — the matching tolerance profile
  (per-attribute up/down bands, most active, depth/table/angles inactive).
- Both permission tables are **empty**.

How full are the new columns?

| Column | Populated | Of | % |
|---|---:|---:|---:|
| `tblPlanMaster.IsMatchPair = 1` | 0 | 1,316,677 | 0.00% |
| `tblPlanMaster.MatchPairId` | 0 | 1,316,677 | 0.00% |
| `tblPlanMaster.Length` / `Width` | 13 | 1,316,677 | 0.00% |
| `tblPlanMaster.OrderDetailId` | 182 | 1,316,677 | 0.01% |
| `tblPacket.OrderDetailId` | 16 | 172,233 | 0.01% |

`OrderDetailId` holds GUIDs, first written **2026-08-21** — the backup's own last
day — and there is **no populated order table** for them to point at
(`tblOrderDisplay` is empty).

So both features are configured but **not yet in use**, and there are two ways to
answer them wrongly: report 664 as a number of *pairs*, or read `IsMatchPair`,
get 0, and present it as if pairing had failed. The `match_pair_and_orders` rule
in `query_rules.py` makes the model say the feature carries no production data
yet instead.

**The schema layer reads new tables and columns automatically** — `get_tables()` /
`get_columns()` query `sys.tables`/`sys.columns` live, so a restore is picked up
on the next backend restart (in-process `lru_cache`, no Redis cache to clear).
Verified: all 97 `tblPlanMaster` columns and all 4 new tables are visible, and the
router surfaces them for match-pair phrasings. What does **not** arrive
automatically is *meaning* — a new table gets a raw column list and no note.

---

## 6. Coverage traps when joining

Inner joins silently shrink answers. LEFT JOIN and state the coverage.

- `tblFinalPacket` → `tblPctChecker`: **38.3%** of 2026 final packets. An
  employee-wise production report built on it understates every worker.
- `tblPacket` → `tblPacketDetail`: **72.7%** of 2026 packets, and
  `tblPacketDetail` has no usable date column (it died in 2017) — scope on
  `tblPacket.CreDate` instead.

---

## 7. The client's own definitions are IN the database

Found 2026-08-27, while chasing three wrong answers. We had been reconstructing
the client's business rules from screenshots and meetings. We did not need to —
**their ERP's own SQL ships inside the backup**, in `sys.sql_modules`:

```sql
SELECT o.name, o.type_desc, m.definition
FROM sys.objects o JOIN sys.sql_modules m ON o.object_id = m.object_id
WHERE m.definition LIKE '%<the stage or column you care about>%';
```

The ones that matter so far:

| Object | What it defines |
|---|---|
| `GetPLSSUM`, `GetChkPLSSUM` | PLS value for packets **not yet GIA'd** — the "pending" anti-join |
| `GetMFGSUMBYLAB`, `GetPLSSUMBYLAB` | the same, split by certifying lab, via the **`LAB` column** |
| `GetMFGSUM`, `GetChkMFGSUM` | MFG value for packets not yet assorted |
| `sp_GetKapanPerformance`, `sp_GetPlanningAssessment` | kapan / planning scorecards |
| `rb_LoadKapanStagesByKapanId` | the full stage ladder for a kapan |

Three things every one of those procs does that our recipes did **not**:

1. `IsDamagePlan = 0` — damaged plans are excluded from every figure.
2. `IsApproved = 1` — unapproved rows are excluded from every figure.
3. **Pending is an anti-join**, never a filter: `Packet_ID NOT IN (SELECT
   Packet_ID ... WHERE RapVer = '<later stage>' AND IsDamagePlan = 0 AND
   IsApproved = 1)`. This is now enforced by the `stage_pending` rule.

**Read the proc before writing a recipe.** It is the client's answer, in their
own words, and it costs one query to find.

### Still open: the lab report is 132.00 low on July

`lab_results_report` matched the client's May screen on all six columns, but for
July 2026 it returns `PLSAmt 146,421.80 / DiffAmt 6,298.98` where the client
reports `146,553.80 / 6,285.42`. Ruled out by measurement (2026-08-27): the
kapan join drops nothing (0 rows), every lab packet has exactly one lab row and
exactly one PLS row (so no PLS-row-selection variant can move the figure — last
by ID, last by date, first, sum-of-all and last-before-the-GIA row all return
146,421.80 to the cent), `IsDamagePlan`/`IsApproved` change nothing for July,
`OAmount`/`SecAmount`/`Rate × PolishedWt` are not the column, and no period
variant shifts the population. **The report itself is built in the ERP's
application layer, not in SQL** — nothing in `sys.sql_modules` mentions `PLSAmt`
or `DiffAmt`. Closing this needs the client's July export or the screen, not
more schema archaeology.

---

## 8. Maintenance — run these after every restore

1. **`tests/test_prompt_freshness.py`** — fails if the prompt names a date the
   database has moved past. This is what caught the "CAP any `tblPointRateLabour`
   query at 2026-06-30" instruction, which after the 21-Aug restore would have
   discarded a complete 25,619-row July and reported a collapse that never
   happened.
2. **`tests/test_lab_results_report.py`** — fails if the ERP-verified lab figures
   move.
3. Rebuild this document.

Dates in the prompt must be **placeholders**, never literals, unless the feed is
genuinely dead: `{DATA_CUTOFF}` and `{FEED_END:Table.Column}` are filled from the
live database when the prompt is built.

Every rule in `app/agent/query_rules.py` carries the figure it was verified with.
**Do not add one without a number to back it.**
