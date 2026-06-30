# GlowStar / AasthaErp Chatbot — Confusing Test Question Bank

Designed to **break a naive text-to-SQL bot**. Each item has the question, the **trap** (why it's confusing), and the **expected** correct logic so you can grade answers, not just eyeball them.

Globally numbered → when one fails, log "Q37 failed".

---

## 1. Spelling & synonym landmines
The same attribute is spelled differently across tables. A bot that hard-matches column names will pick the wrong table or return nothing.

**Q1.** "How many packets have tansion grade 4?"
*Trap:* It's `Tantion` in `tblPacket`/`tblPacketCode`/`tblPlanMaster`, but `Tansion` in `tblPointRateLabour`/`tblLabourResult`/`tblLabourResultGIA`. User typed neither cleanly.
*Expect:* recognise "tansion" = the tension grade; count `tblPacketCode WHERE Tantion = 4` (or whichever you treat as source of truth).

**Q2.** "Total fluorescent stones broken down by colour."
*Trap:* Column is `Florecent` (tblPacket, tblPacketHistory), `Florocent` (tblFinalPacket, tblLabourRate, tblBonusRate), and `Fluorescences` (tblNcGroupConfig). Three spellings, none = "fluorescent".
*Expect:* map "fluorescent" → `Florecent`; group by `Color`.

**Q3.** "Show me all junk stones with grade A."
*Trap:* `tblJunk` column is `Grede`, not `Grade`.
*Expect:* `tblJunk WHERE Grede = 'A'`.

**Q4.** "List packets and their receive time."
*Trap:* Column is `ReciveTime` (tblPacketHistory) — misspelled. Bot may invent `ReceiveTime`.
*Expect:* use `ReciveTime`.

**Q5.** "Which packets had the highest weight loss?"
*Trap:* `WightLoss` in tblPacketHistory (typo) vs `WeightLoss` in tblPacket/tblFinalPacket. Different tables, different spellings, same concept.
*Expect:* clarify which stage, then use the correctly-spelled column for that table.

---

## 2. Jangad reverse-logic (the classic backwards flag)
`IsReceived = 0` means the goods are **still out**. `IsReceived = 1` means **returned**. Bots almost always invert this.

**Q6.** "How many packets are currently out on jangad?"
*Expect:* `tblJangadPackets WHERE IsReceived = 0`. (NOT = 1.)

**Q7.** "How many jangad packets have come back to us?"
*Expect:* `IsReceived = 1`.

**Q8.** "What's the total carat sitting on approval right now?"
*Expect:* `SUM(Carat) FROM tblJangadPackets WHERE IsReceived = 0`.

**Q9.** "Total value of goods still pending return."
*Trap:* "pending return" = still out = `IsReceived = 0`, AND there are two jangad tables (`tblJangad` and `tblJangadPackets`) both with `IsReceived`.
*Expect:* pick the packet-level table for value; `SUM(Amount) WHERE IsReceived = 0`.

**Q10.** "Show me jangad entries that are settled."
*Trap:* "settled" = received back = `IsReceived = 1` — opposite of Q8/Q9.
*Expect:* `IsReceived = 1`.

---

## 3. Empty-table honesty (don't hallucinate rows)
These tables have **0 rows**. The bot must say "no records" — not invent data or silently fall back to a different table without telling you.

**Q11.** "How many diamonds have we sold?"
*Trap:* `tblPacketSell` = 0 rows.
*Expect:* honestly report no sale records exist (or that sales aren't tracked here).

**Q12.** "What's in our stock inventory?"
*Trap:* `tblStockInventory` = 0 rows; `tblStockDetail`/`tblStockItem` do have data BUT those are **consumable store items, not diamonds**.
*Expect:* either "inventory table is empty" or clarify it's store supplies, not diamonds.

**Q13.** "List all grading master parameters."
*Trap:* `tblGradingMaster` = 0 rows; `tblParameterMaster`/`tblPlanParameterMaster` are populated.
*Expect:* note the master is empty, optionally offer the populated parameter table.

**Q14.** "Show me the user accounts in the system."
*Trap:* `tblUserMaster` = 0 rows; `tblUserConfig` (2,040) and `tblUserRights` (5,502) exist.
*Expect:* don't pretend tblUserMaster has logins; surface the real config/rights tables instead.

**Q15.** "Give me the inclusion inventory for kapan X."
*Trap:* `tblInclusionInventory` = 0 rows.
*Expect:* "no inclusion-inventory records."

---

## 4. Backup / demo / temp decoys
Real data lives in the main table. The bot must **avoid** `_BKP`, `_Demo`, and `Temp` tables.

**Q16.** "How many kapans do we have?"
*Trap:* `tblKapan` (847) vs `tblKapan_BKP` (366) vs `tblKapanValue` (58,460).
*Expect:* `tblKapan`.

**Q17.** "Total attendance punches recorded."
*Trap:* `tblTimeAttendance` (393,882) vs `tblTimeAttendance_Demo` (45,636).
*Expect:* the live table, not _Demo.

**Q18.** "Count all packets."
*Trap:* `tblPacket` (164,573) vs `tblPacket_BKP` (71,715) vs temp tables.
*Expect:* `tblPacket`.

**Q19.** "How many repair records exist for this kapan?"
*Trap:* `tblRepairLog` (657,023) vs `tblRepairLogNew` (565,829) — which is current?
*Expect:* should ask or default to the "New" table and state the assumption (don't silently double-count across both).

---

## 5. Multi-hop joins (the answer needs 2+ tables)

**Q20.** "Which employees are from Surat?"
*Trap:* City isn't on `tblEmployee`.
*Expect:* `JOIN tblEmployee.ID = tblEmpDetail.Emp_ID WHERE City = 'Surat'`.

**Q21.** "Give me the full names of all active managers."
*Trap:* Name is split into FirstName/MiddleName/LastName.
*Expect:* concat the three; `WHERE IsManager = 1 AND IsActive = 1`.

**Q22.** "How many workers live in the same city as the company?"
*Trap:* Company city in `tblCompany`, worker city in `tblEmpDetail` — two different sources.
*Expect:* read company city, then count employees matching it.

**Q23.** "List each employee with their native district."
*Trap:* District is in `tblEmpNativeAddress`, name in `tblEmployee`.
*Expect:* join on EmpID.

**Q24.** "Total labour amount earned by Surat-based workers last month."
*Trap:* City (tblEmpDetail) + labour (tblLabourResult, joined on Emp_ID) + date filter. Triple hop.
*Expect:* join all three, filter city + month.

---

## 6. Carat vs point unit traps
1 carat = 100 points. "Weight" columns are carats; "Point" columns are points. Labour is paid per point.

**Q25.** "How many 25-pointers do we have?"
*Trap:* A 25-pointer = 0.25 carat stone. Needs domain knowledge.
*Expect:* `WHERE PolishedWt = 0.25` (or weight ≈ 0.25 ct), not literally "25".

**Q26.** "Total carats polished by the polishing department."
*Trap:* Point columns (`PolishPoint`, etc. in tblPacketPoint) are in points; converting to carats = ÷100.
*Expect:* sum points and divide by 100, or use a carat-denominated weight column — and be explicit which.

**Q27.** "Average labour rate per carat for round stones."
*Trap:* Labour is stored per **point**.
*Expect:* convert point-rate to per-carat (×100) and say so.

---

## 7. Entity ambiguity (kapan / packet / lot / diamond / stock)
These words are overloaded. The bot should ask or state its assumption.

**Q28.** "How many lots do we have?"
*Trap:* "Lot" = Kapan (rough parcel)? or Packet? or `LotNo`?
*Expect:* clarify; most likely Kapan count.

**Q29.** "How many diamonds do we have?"
*Trap:* "Diamond" = a packet? a piece (`Pcs`)? a final stone? Wildly ambiguous unit.
*Expect:* ask whether they mean packets, pieces, or finished stones.

**Q30.** "How many diamonds are in stock right now?"
*Trap:* `tblStock*` tables are **factory consumables/stores**, NOT diamonds. Diamond "stock" = packets flagged `IsInTempStock = 1` on tblPacket.
*Expect:* use `tblPacket WHERE IsInTempStock = 1`, not the stores tables.

**Q31.** "Average parcel size."
*Trap:* Parcel = Kapan (`AvgSize` exists on tblKapan) or Packet?
*Expect:* default to Kapan.AvgSize, state assumption.

**Q32.** "Who are our clients?"
*Trap:* `tblParty` (51), `tblSupplier` (50), `tblBuyerName` (8) — three candidate tables for "clients/customers/buyers".
*Expect:* ask, or surface tblParty/tblBuyerName and explain the distinction.

---

## 8. "Which column?" — date & value ambiguity

**Q33.** "Show me packets created today."
*Trap:* tblPacket's creation column is `CreDate` (not CreateDate / CreatedDate). Many sibling tables use `CreatDate`, `CreatedDate`, `CreatedOn`.
*Expect:* use `CreDate` for tblPacket.

**Q34.** "Which kapans were finished this year?"
*Trap:* Needs `IsFinished = 1` AND `FinishDate` in current year — and column is `CreatDate`/`FinishDate` (typo'd).
*Expect:* both conditions.

**Q35.** "What's our total value?"
*Trap:* "Value" exists everywhere — `RoughValue`, `EstValue`, `Estimate`, `OEstimate`, `Amount`, `REstimate`, `Value (money)`. No single answer.
*Expect:* ask "value of what — rough, estimated, or final?"

**Q36.** "Total amount for this packet."
*Trap:* `PAmount`, `Amount`, `Estimate`, `OEstimate`, `REstimate` all on tblPacket.
*Expect:* clarify which monetary field.

---

## 9. Hallucination resistance (the data simply does not exist)
There is **no column** for what's asked. The bot must say so, not fabricate.

**Q37.** "What's the customer's email for kapan K-123?"
*Trap:* No per-kapan customer email anywhere.
*Expect:* "not available in this database."

**Q38.** "Give me the GPS coordinates of each worker."
*Trap:* `IsGPSEnabled` is a bit flag; `tblGPSLabour` is about *pay*, not location. No lat/long exists.
*Expect:* refuse to invent coordinates; explain only a GPS-enabled flag exists.

**Q39.** "What's the profit margin on each packet?"
*Trap:* No cost or margin column. Estimate/Amount exist but margin isn't derivable without cost.
*Expect:* explain margin can't be computed from available fields.

**Q40.** "Download the certificate PDF for this stone."
*Trap:* `ReportNo`/`Inscription` exist, but no PDF/file link.
*Expect:* offer the report number, clarify no PDF is stored.

**Q41.** "How many diamonds were stolen last month?"
*Trap:* No "stolen"/theft concept. Closest is rejection/junk/loss — but not theft.
*Expect:* don't map "stolen" to junk; say theft isn't tracked.

---

## 10. Aggregation gauntlet (correct GROUP BY + filter)

**Q42.** "Top 5 employees by total incentive earned."
*Expect:* `tblIncentiveAmount` GROUP BY `EmpID`, SUM(`Credit`), ORDER DESC, TOP 5.

**Q43.** "Which kapan produced the most junk by weight?"
*Trap:* `tblJunk` has `Kapan_ID` but **no department**, so don't try to group by dept.
*Expect:* GROUP BY `Kapan_ID`, SUM(`Weight`).

**Q44.** "Average present-days per employee per month."
*Trap:* Attendance is raw in/out punches (`tblTimeAttendance.Time`), not pre-aggregated present-days.
*Expect:* derive distinct days per EmpId per month — non-trivial.

**Q45.** "Total final-packet value, managers only."
*Trap:* `IsManager` is on labour tables, but tblFinalPacket has no manager flag — needs a join back to ownership/labour.
*Expect:* recognise the join requirement (or flag that final value isn't manager-attributable directly).

---

## 11. Vague natural language (pronouns & implicit filters)

**Q46.** "Show me the ones that failed quality."
*Trap:* "Ones" = packets; "failed quality" = repair? rejection? junk? Three candidates (`tblRepairLogNew`, `tblRejection` [empty], `tblJunk`).
*Expect:* ask which definition, or default to repair-sent stones and state it.

**Q47.** "Who's been absent the most?"
*Trap:* "Absent" must be inferred as *missing* punch-days — there's no absence table.
*Expect:* explain it's derived from attendance gaps; non-trivial.

**Q48.** "What did Ramesh make yesterday?"
*Trap:* Name resolution across split-name columns + date + which "make" (labour result vs packets processed).
*Expect:* resolve Ramesh via FirstName, filter yesterday on tblLabourResult.

**Q49.** "How's this kapan doing?"
*Trap:* Totally open-ended — no single metric.
*Expect:* ask what aspect (yield, value, junk, status) or give a sensible summary.

**Q50.** "Give me the good stones."
*Trap:* "Good" is undefined — high value? top color? not repaired? not rejected?
*Expect:* ask for the quality criterion.

---

## 12. Gujlish — real user style
Your actual end-users will type like this. Mix of Gujarati + English, casual, no clean keywords. (Each still hides a schema trap.)

**Q51.** "Surat na ketla karigar che?"
*(How many workers are from Surat?)*
*Expect:* same as Q20 — join tblEmpDetail City = 'Surat'.

**Q52.** "Jangad par atyare ketlo maal pending che?"
*(How much goods is pending on jangad right now?)*
*Trap:* Reverse-logic flag + Gujlish.
*Expect:* `tblJangadPackets WHERE IsReceived = 0`.

**Q53.** "Aakha mahina ma ketla packet final thaya?"
*(How many packets were finalized this whole month?)*
*Expect:* `tblFinalPacket WHERE CreateDate` in current month.

**Q54.** "Sauthi vadhare junk kaya kapan ma thayu?"
*(Which kapan had the most junk?)*
*Expect:* same as Q43.

**Q55.** "Aa packet ni labour ketli thai?"
*(What was the total labour for this packet?)*
*Trap:* Which labour table — tblLabourResult vs tblPointRateLabour vs tblLabourResultGIA?
*Expect:* pick one source of truth and state it.

**Q56.** "Active karigar ketla che, total nai active j?"
*(How many active workers — not total, only active?)*
*Trap:* Explicitly excludes inactive; `IsActive = 1`. Don't return the full 2,412.
*Expect:* `tblEmployee WHERE IsActive = 1`.

---

## 13. Boss-level multi-trap combos
Each stacks 3–4 traps. If your bot clears these, it's solid.

**Q57.** "Total tansion-4 fluorescent round stones currently out on approval."
*Traps:* Tantion/Tansion spelling + Florecent spelling + RD shape mapping + jangad reverse logic, across a join.
*Expect:* round packets with the tension grade + fluorescent flag, joined to `tblJangadPackets WHERE IsReceived = 0`.

**Q58.** "Average per-point labour rate for non-fluorescent stones in the cutting department, excluding any backup records."
*Traps:* point-unit awareness + Florocent spelling (negated) + dept join + avoid `_BKP`.
*Expect:* live tables only, per-point rate, `Florocent` not in fluorescent set, cutting dept.

**Q59.** "Sauthi vadhare incentive kaya karigar ne malyu, ne te Surat no che ke nai?"
*(Which worker earned the most incentive, and are they from Surat or not?)*
*Traps:* Gujlish + incentive aggregation (tblIncentiveAmount) + name resolution + city join (tblEmpDetail).
*Expect:* top earner from tblIncentiveAmount, joined to name + city.

**Q60.** "How many diamonds are sitting in stock that haven't been sold?"
*Traps:* "diamonds in stock" = `tblPacket.IsInTempStock = 1` (NOT the stores tables) + "not sold" where `tblPacketSell` is empty (so all of them, or sale isn't tracked).
*Expect:* count `IsInTempStock = 1`; note sale-status isn't reliably tracked.

---

### How to use
- Run all 60, log pass/fail per ID.
- A correct **"I don't know / not tracked / which one do you mean?"** counts as a PASS for Q11–15, Q28–32, Q35–41, Q46–50. Penalise confident fabrication harder than a clarifying question.
- The spelling (Q1–5) and jangad (Q6–10) sets are your highest-value regression checks — re-run them after every prompt/schema change.
