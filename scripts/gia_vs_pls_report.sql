/* =========================================================================
   GIA vs PLS grading comparison — the client's report, runnable in SSMS.

   Same logic as the client's parameterised query; the @params are DECLAREd at
   the top so you can just edit the three values and run.

   Verified on AasthaErp_new: June 2026 (all kapans) = 3,584 rows, 1,579 with
   a grade change.
   ========================================================================= */

DECLARE @StartDate date = '2026-06-01';
DECLARE @EndDate   date = '2026-06-30';

/* Kapan filter — pick ONE of the three options below.
   Option A (default): ALL kapans in the period — leave @KapanName NULL.
   Option B: one kapan by NAME, e.g. 'OE26'.
   Option C: several kapan IDs — see the commented AND clause further down. */
DECLARE @KapanName varchar(50) = NULL;   -- e.g. 'OE26', or NULL for all

SELECT
    p.ID,
    p.KapanName,
    p.PacketNo,

    -- in-house (PLS) grading
    pls.Shape,
    pls.Color,
    pls.Cut,
    pls.Polish,
    pls.Symmetry,
    pls.Florecent,
    pls.PolishedWt,
    pls.Purity,
    pls.Amount              AS PLSAmount,
--
    -- lab (GIA / HRD / IGI) grading
    gia.Shape               AS GIA_Shape,
    gia.Color               AS GIA_Color,
    gia.Cut                 AS GIA_Cut,
    gia.Polish              AS GIA_Polish,
    gia.Symmetry            AS GIA_Symmetry,
    gia.Florecent           AS GIA_Florecent,
    gia.PolishedWt          AS GIA_PolishedWt,
    gia.Purity              AS GIA_Purity,
    gia.Amount              AS GIAAmount,
    gia.LAB                 AS LAB,

    /* Did the lab change ANY grade?
       ISNULL(...) on both sides: in T-SQL "x <> NULL" is UNKNOWN, so a NULL on
       either side would silently score as "no change". (On June 2026 data both
       forms give 1,579 — but that is luck, not a guarantee.) */
    CASE
        WHEN (ISNULL(pls.Color,      '') <> ISNULL(gia.Color,      '') OR
              ISNULL(pls.Cut,        '') <> ISNULL(gia.Cut,        '') OR
              ISNULL(pls.Polish,     '') <> ISNULL(gia.Polish,     '') OR
              ISNULL(pls.Symmetry,   '') <> ISNULL(gia.Symmetry,   '') OR
              ISNULL(pls.Florecent,  '') <> ISNULL(gia.Florecent,  '') OR
              ISNULL(pls.PolishedWt,  0) <> ISNULL(gia.PolishedWt,  0) OR
              ISNULL(pls.Purity,     '') <> ISNULL(gia.Purity,     ''))
        THEN 1 ELSE 0
    END                     AS HasChange

FROM tblPacket p WITH (NOLOCK)
INNER JOIN tblPlanMaster gia WITH (NOLOCK)
        ON p.ID = gia.Packet_ID
       AND gia.RapVer IN ('GIA','HRD','IGI')
INNER JOIN tblPlanMaster pls WITH (NOLOCK)
        ON p.ID = pls.Packet_ID
       AND pls.RapVer = 'PLS'

WHERE CAST(gia.CreatDate AS DATE) BETWEEN @StartDate AND @EndDate
  AND (@KapanName IS NULL OR p.KapanName = @KapanName)        -- Option A / B

  /* Option C — specific kapan IDs (uncomment and list them):
  AND p.Kapan_ID IN (1508, 1510, 1531)
  */

ORDER BY p.KapanName, p.PacketNo;


/* -------------------------------------------------------------------------
   Variant 1 — SUMMARY: regrade rate per kapan
   ------------------------------------------------------------------------- */
/*
SELECT p.KapanName,
       COUNT(*)                                            AS Packets,
       SUM(CASE WHEN ISNULL(pls.Color,'')<>ISNULL(gia.Color,'')
                  OR ISNULL(pls.Purity,'')<>ISNULL(gia.Purity,'')
                  OR ISNULL(pls.Cut,'')<>ISNULL(gia.Cut,'')
                  OR ISNULL(pls.Polish,'')<>ISNULL(gia.Polish,'')
                  OR ISNULL(pls.Symmetry,'')<>ISNULL(gia.Symmetry,'')
                THEN 1 ELSE 0 END)                         AS Changed,
       CAST(100.0 * SUM(CASE WHEN ISNULL(pls.Color,'')<>ISNULL(gia.Color,'')
                  OR ISNULL(pls.Purity,'')<>ISNULL(gia.Purity,'')
                THEN 1 ELSE 0 END) / COUNT(*) AS decimal(5,1)) AS ChangedPct
FROM tblPacket p WITH (NOLOCK)
INNER JOIN tblPlanMaster gia WITH (NOLOCK) ON p.ID=gia.Packet_ID AND gia.RapVer IN ('GIA','HRD','IGI')
INNER JOIN tblPlanMaster pls WITH (NOLOCK) ON p.ID=pls.Packet_ID AND pls.RapVer='PLS'
WHERE CAST(gia.CreatDate AS DATE) BETWEEN @StartDate AND @EndDate
GROUP BY p.KapanName
ORDER BY Changed DESC;
*/


/* -------------------------------------------------------------------------
   Variant 2 — the same report WITH THE MAKER AND DEPARTMENT
   (what the client asked for: who made it, and in which department).
   The maker is the packet's LATEST MFG-stage row; OUTER APPLY + LEFT JOIN so a
   packet is never dropped. Verified: resolves for 100% of finished packets.
   ------------------------------------------------------------------------- */
/*
SELECT p.KapanName, p.PacketNo,
       e.FirstName + ' ' + e.LastName AS Maker,
       e.DepartMentName               AS Department,
       pls.Color AS PLS_Color, gia.Color AS GIA_Color,
       pls.Purity AS PLS_Clarity, gia.Purity AS GIA_Clarity,
       pls.Cut AS PLS_Cut, gia.Cut AS GIA_Cut,
       gia.PolishedWt, gia.LAB,
       CONVERT(varchar(10), gia.CreatDate, 105) AS GIA_Date
FROM tblPacket p WITH (NOLOCK)
INNER JOIN tblPlanMaster gia WITH (NOLOCK) ON p.ID=gia.Packet_ID AND gia.RapVer IN ('GIA','HRD','IGI')
INNER JOIN tblPlanMaster pls WITH (NOLOCK) ON p.ID=pls.Packet_ID AND pls.RapVer='PLS'
OUTER APPLY (SELECT TOP 1 EmpId FROM tblPlanMaster WITH (NOLOCK)
             WHERE Packet_ID = p.ID AND RapVer='MFG' ORDER BY ID DESC) m
LEFT JOIN tblEmployee e ON m.EmpId = e.ID
WHERE CAST(gia.CreatDate AS DATE) BETWEEN @StartDate AND @EndDate
ORDER BY p.KapanName, p.PacketNo;
*/
