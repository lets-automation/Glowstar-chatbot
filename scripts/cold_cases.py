"""
cold_cases.py
-------------
COLD TEST — client-realistic questions with NO encoded guidance, each paired with
a ground-truth SQL that was RUN against the DB when the case was written.

This is how we measure preparedness for questions nobody anticipated, instead of
guessing at it. Many are Gujlish, several are deliberately unanswerable (the
honest reply is "that is not recorded"), and a few are ambiguous and should draw
a clarification rather than a number.

Used by scripts/cold_test.py. Ground truth is re-computed at run time, so a DB
refresh updates the expectation automatically — truthValue is the value observed
on the 2026-07-27 backup and is kept only as a tripwire for schema drift.
"""

COLD_CASES = [
    # --- packet / production core -------------------------------------------
    {"id": "COLD-01", "question": "last month ketla stone lab ma send karya?",
     "truthSql": "SELECT COUNT(DISTINCT Packet_ID) AS StonesSentToLab FROM tblPlanMaster WITH (NOLOCK) WHERE RapVer IN ('GIA','HRD','IGI') AND CreatDate >= '2026-06-01' AND CreatDate < '2026-07-01'",
     "truthValue": "3584"},
    {"id": "COLD-02", "question": "June ma manufacturing ma ketlu value loss thayu?",
     "truthSql": "SELECT CAST(SUM(ISNULL(WightLoss,0)) AS decimal(14,3)) AS WeightLossCarats FROM tblPacketHistory WITH (NOLOCK) WHERE ReciveTime >= '2026-06-01' AND ReciveTime < '2026-07-01'",
     "truthValue": "1382.894"},
    {"id": "COLD-03", "question": "aa varsh ma ketla planning verify thaya che?",
     "truthSql": "SELECT COUNT(*) AS PlansApproved2026 FROM tblPlanMaster WITH (NOLOCK) WHERE CreatDate >= '2026-01-01' AND IsApproved = 1",
     "truthValue": "148887"},
    {"id": "COLD-04", "question": "atyare ketla diamond hold par che?",
     "truthSql": "SELECT COUNT(*) AS PacketsOnHold FROM tblPacket p WITH (NOLOCK) JOIN tblKapan k WITH (NOLOCK) ON p.Kapan_ID = k.ID WHERE k.IsOnHold = 1",
     "truthValue": "11835"},
    {"id": "COLD-05", "question": "how many stones are out on memo right now?",
     "truthSql": "SELECT COUNT(*) AS PacketsOnMemo FROM tblPacket WITH (NOLOCK) WHERE IsOnMemo = 1",
     "truthValue": "527"},
    {"id": "COLD-06", "question": "kapan OQ26 ma total ketla piece hata?",
     "truthSql": "SELECT TotalPcs AS OriginalRoughPieces FROM tblKapan WITH (NOLOCK) WHERE KapanName = 'OQ26'",
     "truthValue": "585"},
    {"id": "COLD-07", "question": "OQ26 kapan ma final point / final polish weight ketlu nikalyu?",
     "truthSql": "SELECT CAST(SUM(ISNULL(p.CurrentWt,0)) AS decimal(12,3)) AS PolishedCarats FROM tblPacket p WITH (NOLOCK) JOIN tblKapan k WITH (NOLOCK) ON p.Kapan_ID = k.ID WHERE k.KapanName = 'OQ26'",
     "truthValue": "523.897"},
    {"id": "COLD-08", "question": "how many oval diamonds do we have in stock?",
     "truthSql": "SELECT COUNT(*) AS OvalPacketsInStock FROM tblPacket WITH (NOLOCK) WHERE RunningProcess = 'IN Stock' AND Shape IN ('OV','F.OV','S.OV','OVM')",
     "truthValue": "7321"},
    {"id": "COLD-09", "question": "our stock na stone no average depth % ketlo che?",
     "truthSql": "SELECT CAST(AVG(pp.DepthPer) AS decimal(8,3)) AS AvgDepthPct FROM tblPacket p WITH (NOLOCK) JOIN tblPacketParameters pp WITH (NOLOCK) ON pp.PacketID = p.ID WHERE p.RunningProcess = 'IN Stock' AND ISNULL(pp.DepthPer,0) > 0",
     "truthValue": "62.937"},

    # --- jangad / parties ----------------------------------------------------
    {"id": "JP-1", "question": "Water jet ma total ketla jangad gaya che? Water Jet process ma kul ketli entry chhe?",
     "truthSql": "SELECT COUNT(*) AS WaterJetJangads FROM tblJangad WITH (NOLOCK) WHERE REPLACE(Process,' ','') LIKE '%WATERJET%'",
     "truthValue": "2437"},
    {"id": "JP-2", "question": "Galaxy process no rate su chhe? Party ne galaxy na ketla paisa apiye chhiye?",
     "truthSql": "SELECT COUNT(*) AS GalaxyRateRows FROM tblJangadRate WITH (NOLOCK) WHERE Process LIKE '%GALAX%'",
     "truthValue": "0"},
    {"id": "JP-3", "question": "Party wise jangad batavo - kaya kaya party pase aapno maal gayo che, GST number sathe",
     "truthSql": "SELECT COUNT(*) AS OrphanIssueJangads FROM tblJangad j WITH (NOLOCK) WHERE j.TransType='Issue' AND NOT EXISTS (SELECT 1 FROM tblParty p WITH (NOLOCK) WHERE p.Name = j.ToParty)",
     "truthValue": "2085"},

    # --- damage / repair / scrap --------------------------------------------
    {"id": "DRS-1", "question": "Aa varshe ketlu bhangar (scrap) bahar issue karyu? Junk kitna nikala this year?",
     "truthSql": "SELECT COUNT(*) AS ScrapIssuedThisYear FROM tblJunk WITH (NOLOCK) WHERE IsIssed=1 AND CreateDate >= '2026-01-01'",
     "truthValue": "0"},
    {"id": "DRS-2", "question": "2025 ma damage na ketla paisa katya karigar pase thi? Damage deduction total kitna hua?",
     "truthSql": "SELECT CAST(SUM(Amount) AS decimal(18,2)) AS Damage2025 FROM tblPlanReport WITH (NOLOCK) WHERE IsDamageReport=1 AND CreatedDate >= '2025-01-01' AND CreatedDate < '2026-01-01'",
     "truthValue": "-11536.82"},
    {"id": "DRS-3", "question": "Repair kya reason thi aave chhe? Sauthi vadhare kyu reason chhe repair ma?",
     "truthSql": "SELECT COUNT(*) AS PolishRepairs FROM tblRepairCommentVision WITH (NOLOCK) WHERE RepairComment='Polish'",
     "truthValue": "1906"},

    # --- employees / departments / attendance --------------------------------
    {"id": "EDA-1", "question": "Aaje factory ma total ketla mansu (worker) chhe? Aapna kul employee kitne hain?",
     "truthSql": "SELECT MAX(Date) AS LastHeadcountDate FROM tblEmployeeCount WITH (NOLOCK)",
     "truthValue": "2021-07-23 00:00:00"},
    {"id": "EDA-2", "question": "Aapne ketla department chalu chhe? Kitne department active hain abhi?",
     "truthSql": "SELECT COUNT(*) AS DeptsWithActiveStaff FROM tblDepartMent d WITH (NOLOCK) WHERE EXISTS (SELECT 1 FROM tblEmployee e WITH (NOLOCK) WHERE e.DepartMent_ID = d.ID AND e.IsActive = 1)",
     "truthValue": "62"},
    {"id": "EDA-3", "question": "Employee rating ma sauthi saru kon chhe? Konu performance rating best chhe?",
     "truthSql": "SELECT COUNT(DISTINCT r.EmpId) AS ActiveEmployeesWithRating FROM tblEmpRating r WITH (NOLOCK) JOIN tblEmployee e WITH (NOLOCK) ON e.ID = r.EmpId WHERE e.IsActive = 1",
     "truthValue": "9"},

    # --- statutory / untracked concepts / ambiguity ---------------------------
    {"id": "CT-01", "question": "Sir ne PF ane ESIC nu record joie che - badha employee na PF number ane ESIC number ni list kadhi aapo.",
     "truthSql": "SELECT COUNT(NULLIF(LTRIM(RTRIM(ISNULL(PFNumber,''))),'')) + COUNT(NULLIF(LTRIM(RTRIM(ISNULL(ESIC,''))),'')) AS employees_with_pf_or_esic FROM tblEmpDetail WITH (NOLOCK)",
     "truthValue": "0"},
    {"id": "CT-02", "question": "Junk nu grade-wise report kadho - kaya grade ma ketlu weight ane ketla pcs padya che?",
     "truthSql": "SELECT COUNT(DISTINCT Grede) AS distinct_junk_grades FROM tblJunk WITH (NOLOCK) WHERE NULLIF(LTRIM(RTRIM(ISNULL(Grede,''))),'') IS NOT NULL",
     "truthValue": "0"},
    {"id": "CT-03", "question": "RFID wise packet tracking nikalo - abhi kaunsa packet kaunse RFID tag pe hai?",
     "truthSql": "SELECT COUNT(*) AS packets_with_rfid FROM tblPacket WITH (NOLOCK) WHERE NULLIF(LTRIM(RTRIM(ISNULL(RFID,''))),'') IS NOT NULL",
     "truthValue": "0"},
    {"id": "CT-04", "question": "Chalu mahina no employee-wise labour amount joie - kaya karigar ne ketla rupiya thaya?",
     "truthSql": "SELECT COUNT(*) AS labourresult_rows_last_24_months FROM tblLabourResult WITH (NOLOCK) WHERE ProcessDate >= '2024-08-01'",
     "truthValue": "0"},
    {"id": "CT-05", "question": "Aa mahine ketla nang vechya ane ketla dollar aavya? Buyer-wise sale batavo.",
     "truthSql": "SELECT COUNT(*) AS sale_records_ever FROM tblPacketSell WITH (NOLOCK)",
     "truthValue": "0"},
    {"id": "CT-07", "question": "Aa mahine ketla nang thaya?",
     "truthSql": "SELECT MAX(v)-MIN(v) AS spread_between_readings FROM ( SELECT COUNT(*) v FROM tblPacket WITH (NOLOCK) WHERE CreDate>='2026-07-01' AND CreDate<'2026-08-01' UNION ALL SELECT COUNT(*) FROM tblPacket WITH (NOLOCK) WHERE PolishDate>='2026-07-01' AND PolishDate<'2026-08-01' UNION ALL SELECT COUNT(*) FROM tblFinalPacket WITH (NOLOCK) WHERE CreateDate>='2026-07-01' AND CreateDate<'2026-08-01' UNION ALL SELECT ISNULL(SUM(CAST(Pcs AS bigint)),0) FROM tblPacket WITH (NOLOCK) WHERE CreDate>='2026-07-01' AND CreDate<'2026-08-01' ) x",
     "truthValue": "1832"},
    {"id": "CT-08", "question": "Kapan nu yield batavo.",
     "truthSql": "SELECT COUNT(*) AS yield_or_recovery_columns_in_db FROM INFORMATION_SCHEMA.COLUMNS WHERE COLUMN_NAME LIKE '%yield%' OR COLUMN_NAME LIKE '%recover%'",
     "truthValue": "0"},
    {"id": "CT-09", "question": "Kapan ma ketlo loss thayo? Boil ane chapka bane no loss alag alag batavo.",
     "truthSql": "SELECT COUNT(*) AS kapans_with_chapka_loss FROM tblKapan WITH (NOLOCK) WHERE ISNULL(ChapkaLoss,0) <> 0",
     "truthValue": "1"},
]
