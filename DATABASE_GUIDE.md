# GlowStar / AasthaErp - Database Guide

Complete data dictionary of the diamond-manufacturing ERP database. Use this to understand the data and frame questions.

- Total business tables: **239**
- Total columns: **2977**
- Foreign-key links: **39**

## Business glossary (diamond-industry terms)

- **Carat**: Diamond weight unit. 1 carat = 200 milligrams.
- **Point**: Fine weight unit. 1 carat = 100 points. A 0.25ct stone is a '25-pointer'. Labour is often paid per point of weight processed.
- **Kapan**: A lot/parcel of ROUGH diamonds bought and processed together as one batch. Most records are tagged with a Kapan_ID/KapanName. A Kapan is split into individual Packets for processing.
- **Packet**: A parcel/lot of diamonds tracked as a single unit as it moves through the factory (planning -> cutting -> polishing -> final). Packets belong to a Kapan.
- **SubPcs**: Sub-pieces - a packet split into smaller pieces.
- **Tantion / Tansion**: Tension grade of the stone (a quality/clarity attribute used in rate calculations). Spelled both 'Tantion' and 'Tansion' in the DB.
- **Jangad**: An entrustment note - diamonds sent out on approval / sale-or-return basis, on trust. Tracks goods given out but not yet sold or returned (common in the Indian diamond trade).
- **Plan / Planning**: Mapping how a rough stone will be cut to maximise value. The first manufacturing stage.
- **Labour Rate**: Piece-rate paid to a worker for processing a diamond, usually per point of weight or per process stage.
- **Point Rate Labour**: The labour rate paid specifically per point of weight.
- **Labour Result**: The output of a worker's processing - pieces completed and resulting yield.
- **Incentive**: Extra pay earned for meeting yield/quality/output targets.
- **Bonus**: Additional reward pay, often rate-based.
- **Repair**: Re-polishing or fixing a stone that did not pass quality.
- **Junk**: Rejected or scrap diamond material.
- **Time Attendance**: Worker attendance records (in/out, present days).
- **Report Rate**: Rates used for reporting / valuation purposes.
- **Fluorescence**: How much a diamond glows under UV. STORED IN A MISSPELLED COLUMN: 'Florecent' (tblPacket, tblPacketHistory, tblPlanMaster, etc.) or 'Florocent' (tblFinalPacket, tblLabourResult, rate tables). There is NO column spelled 'Fluorescent'.

## DATA NOTES (column spellings & how to filter)

- Some columns are misspelled (e.g. fluorescence is 'Florecent'/'Florocent'). If an expected column name isn't found, call get_table_columns to find the real/misspelled variant before concluding the data is missing.
- Column names can be misleading: the 'Purity' column actually holds the CLARITY grade.
- When filtering a coded column, use the CODES below (e.g. Color='D', Florecent<>'NON'), not the full English word.

VALUE CODES (what coded column values mean)

- Shape (column 'Shape'): RD=Round, EM=Emerald, HR=Heart, PS=Pear, OV=Oval, PR=Princess, MQ=Marquise, CU=Cushion, RAD=Radiant, BG=Baguette, TRI=Trillion, SQEM=Square Emerald; 'F.xx' = Fancy and 'S.xx' = special variants. Always filter with the CODE, not the English word.
- Color (column 'Color'): Diamond colour grade: D, E, F, G, H, I, J, K, L, M, N (D = colourless/best, N = most tinted).
- Clarity (stored in the 'Purity' column!): The clarity grade is in a column NAMED 'Purity'. Values best->worst: FL, IF, VVS1, VVS2, VS1, VS2, SI1, SI2, I1, I2, I3.
- Cut / Polish / Symmetry: EX=Excellent, VG=Very Good, GD=Good, FR=Fair.
- Fluorescence (column 'Florecent' or 'Florocent'): NON=None, FNT=Faint, MED=Medium, STG=Strong, VST=Very Strong. A 'fluorescent stone' = value is NOT 'NON'. No column is spelled 'Fluorescent'.
- Process (column 'Process'): The manufacturing stage, e.g. IN Stock, Weight Scale, Marker, Laser, Galaxy, Blocking, Vision 360, Polish Checker, MFG-1, MFG-2, OUT Stock.

## Common ID / join columns (how tables connect)

- **Kapan_ID / KapanName**: the rough-diamond lot. Most production rows carry it.
- **Packet_ID / PacketNo**: a packet within a Kapan.
- **Emp_ID / EmpId / EmpName**: the worker. Emp_ID = tblEmployee.ID.
- **Department_ID / DepartMent_ID**: the process department/stage.
- To get an employee's city: join tblEmployee.ID = tblEmpDetail.Emp_ID, filter tblEmpDetail.City.

## Tables by category (with row counts)

### Packets & Production (43 tables)

- `tblPacketHistory` (5,546,990 rows) - Movement/history of each packet as it passes through process stages.
- `tblPacketIssue` (5,546,849 rows) - Records of packets issued out to workers/processes.
- `tblPacketPoint` (240,901 rows) - Weight (in points) of packets.
- `tblIssuedPacketDetail` (225,625 rows) - Detail lines for issued packets.
- `tblJangadPackets` (190,201 rows) - Packets sent out on jangad (approval / sale-or-return). IsReceived=0 means still OUT ('currently on jangad'); IsReceived=1 means returned/received. To count packets CURRENTLY on jangad, filter WHERE IsReceived = 0.
- `tblFinalPacket` (171,765 rows) - Finished/completed packets.
- `tblPacketDetail` (171,112 rows) - Detailed line items for a packet.
- `tblPacket` (164,573 rows) - Master list of packets (the central packet record other tables link to).
- `tblPacketParameters` (147,636 rows)
- `tblPacketCode` (138,918 rows)
- `tblPacketPointGIA` (75,712 rows)
- `tblPacket_BKP` (71,715 rows)
- `tblKapanValue` (58,460 rows)
- `tblPacketPrint` (31,858 rows)
- `tblPacketOwener` (25,722 rows)
- `tblStockIssueDetail` (16,210 rows)
- `tblStockIssue` (15,947 rows)
- `tblIssuedPacket` (1,585 rows)
- `tblIssuedKapan` (1,365 rows)
- `tblPacketPrintAdditional` (918 rows)
- `tblKapan` (847 rows)
- `tblKapanChallan` (822 rows)
- `tblKtdPacket` (728 rows)
- `tblTestGXKapanPricePlanMaster` (477 rows)
- `tblKapan_BKP` (366 rows)
- `tblTestKapanPricePlanMaster` (184 rows)
- `tblFinalReportSize` (69 rows)
- `tblPendingPacketPoint` (8 rows)
- `tblConfigIssueSizeRanges` (6 rows)
- `tblChkFinalPoint` (3 rows)
- `tblConfigIssueShapeSizes` (2 rows)
- `tblPacketPointReason` (1 rows)
- `tblBulkPacket` (0 rows)
- `tblChkKapanPoint` (0 rows)
- `tblKapanPoint` (0 rows)
- `tblLotPacketDetail` (0 rows)
- `tblPctIssueConfig` (0 rows)
- `tblPacketColor` (0 rows)
- `tblPacketColorAnalysisTemp` (0 rows)
- `tblPacketGenerateTemp` (0 rows)
- `tblPacketSell` (0 rows)
- `tblPacketPointGIAReason` (0 rows)
- `tblPacketNumber` (0 rows)

### Planning & Cutting (9 tables)

- `tblPlanMaster` (1,247,480 rows) - The cutting plan for each rough stone (planning stage).
- `tblPlanMasterOptional` (701,089 rows) - Optional/alternative cutting plans for a stone.
- `tblPlanReport` (100,119 rows)
- `tblPlanMaster_Update` (22,307 rows)
- `tblPlanReport_BKP` (2,712 rows)
- `tblPlanPoint` (233 rows)
- `tblPlanParameterMaster` (114 rows)
- `tblPendingPlan` (85 rows)
- `tblAllowOrderPlanPermission` (47 rows)

### Labour & Payroll (40 tables)

- `tblLabourRate` (3,379,566 rows) - Piece-rates paid to labour per process/stage.
- `tblBonusRate` (1,535,720 rows) - Bonus rate definitions used to calculate bonus pay.
- `tblReportRate` (1,535,720 rows) - Rates used for reporting/valuation.
- `tblPointRateLabour` (875,383 rows) - Labour rate paid per point of weight.
- `tblLabourResult` (623,404 rows) - Output/results of labour processing per worker.
- `tblIncentiveAmount` (604,055 rows) - Incentive payment amounts earned by workers.
- `tblOriginWiseLabour` (123,552 rows)
- `tblLabourResultGIA` (121,337 rows)
- `tblLabourResult_Compare` (95,732 rows)
- `tblEmpGIABonus` (17,304 rows)
- `tblLabourCriteria` (9,149 rows)
- `tblPointRate` (8,040 rows)
- `tblLabourResultEdit` (5,352 rows)
- `tblLabour_MW` (2,561 rows)
- `tblGPSLabour` (506 rows)
- `tblRateGenerator` (177 rows)
- `tblLabourDepConfig` (36 rows)
- `tblEmpGpsLabourDetail` (34 rows)
- `tblPolishCheckerRate` (29 rows)
- `tblPointRateLossSlot` (19 rows)
- `tblPointRateSlot` (19 rows)
- `tblPointRateSlotConfig` (15 rows)
- `tblJangadRate` (8 rows)
- `tblLabourTypeList` (7 rows)
- `tblPointRateTansionConfig` (5 rows)
- `tblGPSLabourRate` (2 rows)
- `tblRateConfig` (1 rows)
- `tblLabourConfig` (1 rows)
- `tblBonusFormula` (0 rows)
- `tblBonusRateManager` (0 rows)
- `tblBulkRate` (0 rows)
- `tblDeptCompareRate` (0 rows)
- `tblLabourCostConfig` (0 rows)
- `tblLabourFormula` (0 rows)
- `tblLabourGrade` (0 rows)
- `tblLabourLimit` (0 rows)
- `tblLabourRateManager` (0 rows)
- `tblLabourResultGIAEdit` (0 rows)
- `tblStaticDepLabour` (0 rows)
- `tblReportRateManager` (0 rows)

### Employees & HR (28 tables)

- `tblTimeAttendance` (393,882 rows) - Worker attendance records.
- `tblTimeAttendance_Demo` (45,636 rows)
- `tblEmp_SPC_Criteria` (30,625 rows)
- `tblLeaveReport` (20,066 rows)
- `tblGraderRemark` (4,156 rows)
- `tblEmployeeTimeAttandance` (2,926 rows)
- `tblEmployee` (2,412 rows) - Master employee records: FirstName, MiddleName, LastName, Code, department, join date, active status. The employee ID is its ID column (referenced elsewhere as Emp_ID / EmpId).
- `tblEmpDetail` (2,411 rows) - Employee personal details: address (City, State, Country, Address1/2), phone, mobile, email. Links to tblEmployee via Emp_ID. To find employees by city, join tblEmployee.ID = tblEmpDetail.Emp_ID and filter on City.
- `tblEmp_Criteria` (2,124 rows)
- `tblEmp_Weight_Criteria` (1,849 rows)
- `tblEmpReference` (1,378 rows)
- `tblEmp_Value_Criteria` (931 rows)
- `tblEmployeeCount` (524 rows)
- `tblEmpNativeAddress` (521 rows)
- `tblRuleTemplateDetail` (173 rows)
- `tblEmpIpAddress` (159 rows)
- `tblEmpSitArrangement` (56 rows)
- `tblPartyEmps` (50 rows)
- `tblEmpRating` (30 rows)
- `tblRuleTemplate` (3 rows)
- `tblEmpGrade` (0 rows)
- `tblEmpEduInfo` (0 rows)
- `tblEmpFamilyInfo` (0 rows)
- `tblEmpConnDept` (0 rows)
- `tblMachineShift` (0 rows)
- `tblEmpWorkExp` (0 rows)
- `tblEmpShiftDetails` (0 rows)
- `tblGraderResult` (0 rows)

### Quality & Repair (20 tables)

- `tblRepairLog` (657,023 rows) - Records of stones sent for repair/re-polish.
- `tblRepairLogNew` (565,829 rows) - Newer repair/re-polish log (possibly replaces tblRepairLog).
- `tblJunk` (201,285 rows) - Rejected/scrap diamond material.
- `tblAIColorPrediction` (56,055 rows)
- `tblRepairCommentVision` (4,363 rows)
- `tblFavouriteReport` (2,222 rows)
- `tblCharacterReport` (769 rows)
- `tblReportItem` (225 rows)
- `tblReportDept` (25 rows)
- `tblReportType` (17 rows)
- `tblReportGroup` (9 rows)
- `tblRepairConfigComment` (8 rows)
- `tblDamageReportType` (8 rows)
- `tblInceDamageReportType` (2 rows)
- `tblMergeReportDepartment` (0 rows)
- `tblUserReports` (0 rows)
- `tblRejection` (0 rows)
- `tblRepairing` (0 rows)
- `tblRepairLoss` (0 rows)
- `tblReportFormula` (0 rows)

### Jangad & Transfer (7 tables)

- `tblJangad` (15,654 rows)
- `tblJangadBranch` (49 rows)
- `tblJangadProcess` (22 rows)
- `tblJangadTag` (2 rows)
- `tblJangadTransType` (0 rows)
- `tblJangadDetail` (0 rows)
- `tblJangadMaster` (0 rows)

### Parties & Business (7 tables)

- `tblCompanySchedule` (8,212 rows)
- `tblDepartMent` (92 rows)
- `tblDeptConfig` (70 rows)
- `tblParty` (51 rows)
- `tblSupplier` (50 rows)
- `tblCompanyType` (2 rows)
- `tblCompany` (1 rows)

### Masters & Config (25 tables)

- `tblRuleDetails` (52,904 rows)
- `tblUserConfig` (2,040 rows)
- `tblGridConfig` (1,994 rows)
- `tblNcGroupConfig` (924 rows)
- `tblGPSDepConfig` (435 rows)
- `tblParameterMaster` (154 rows)
- `tblDep_Criteria` (77 rows)
- `tblRuleList` (35 rows)
- `tblTaskType` (22 rows)
- `tblTaskTypeAction` (16 rows)
- `tblRoughOriginMaster` (14 rows)
- `tblTAMachine` (6 rows)
- `tblNotificationType` (5 rows)
- `tblRejRules` (4 rows)
- `tblSentenceType` (1 rows)
- `tblConfig` (1 rows)
- `tblAppConfig` (1 rows)
- `tblBulkConfig` (0 rows)
- `tblConfigPricingRestricts` (0 rows)
- `tblMachineConfig` (0 rows)
- `tblMfgDaysCriteria` (0 rows)
- `tblGradingMaster` (0 rows)
- `tblUserMaster` (0 rows)
- `tblTaskCanceledType` (0 rows)
- `tblPrintConfig` (0 rows)

### Other (60 tables)

- `tblAllowMKBPermission` (111,473 rows)
- `tblAllowMrkAdminPermission` (108,008 rows)
- `tblDeletedTask` (101,701 rows)
- `tblPctChecker` (94,020 rows)
- `tblParam` (61,279 rows)
- `tblAllowMFGPermission` (32,926 rows)
- `tblChkImprovement` (17,479 rows)
- `tblSmsResponse` (10,208 rows)
- `tblUserRights` (5,502 rows)
- `tblNcGroupAssigned` (4,698 rows)
- `tblTask` (4,350 rows)
- `tblPersonMetaData` (2,939 rows)
- `tblContactMethod` (1,598 rows)
- `tblStockDetail` (1,041 rows)
- `tblStockPurchageDetail` (1,034 rows)
- `tblBoxDetail` (921 rows)
- `tblPermissionDetail` (898 rows)
- `tblGirdleDetail` (866 rows)
- `tblArticle` (790 rows)
- `tblStockPurchage` (661 rows)
- `tblBox` (539 rows)
- `tblDepParaMeter` (525 rows)
- `tblPctAutomation` (463 rows)
- `tblStockItem` (394 rows)
- `tblHemory` (385 rows)
- `tblStockTally` (302 rows)
- `tblCycleParam` (85 rows)
- `tblPermissionList` (64 rows)
- `tblRapVer` (41 rows)
- `tblMine` (40 rows)
- `tblArticleSize` (16 rows)
- `tblNcGroupName` (15 rows)
- `tblStockUnit` (11 rows)
- `tblStockCategory` (9 rows)
- `tblSentence` (8 rows)
- `tblDep_Suggest` (8 rows)
- `tblBuyerName` (8 rows)
- `tblwfCategory` (4 rows)
- `tblwfPriority` (4 rows)
- `tblNotification` (3 rows)
- `tblLoginPopupContents` (3 rows)
- `tblSarineValue` (2 rows)
- `tblStockGodown` (1 rows)
- `tblKoted` (1 rows)
- `tblCompneyOwener` (1 rows)
- `tblAdminPrivilage` (1 rows)
- `tblAuthentication` (0 rows)
- `tblBulkNumber` (0 rows)
- `tblBulkProcess` (0 rows)
- `tblCvdPrice` (0 rows)
- `tblNotifyClient` (0 rows)
- `tblOrderDisplay` (0 rows)
- `tblOrderDisplayCondition` (0 rows)
- `tblInclusionInventory` (0 rows)
- `tblStockInventory` (0 rows)
- `tblStockTallyLog` (0 rows)
- `tblUserGroup` (0 rows)
- `tblTaskCanceled` (0 rows)
- `tblTaskReminder` (0 rows)
- `tblTwoFactorAuth` (0 rows)

## Full data dictionary (all tables and columns)

### Packets & Production

**tblPacketHistory** (5,546,990 rows)
_Movement/history of each packet as it passes through process stages._
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Packet_ID (int), PacketNo (int), SubPcs (varchar), ManagerId (int), ManagerName (varchar), EmpId (int), EmpName (varchar), Process (varchar), Shape (varchar), Purity (varchar), Color (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Weight (decimal), Value (money), ValueLossUp (money), WightLoss (decimal), JunkLoss (decimal), ReciveTime (smalldatetime), UserId (int), UserName (varchar), Pie (int), Saw (int), ToEmpId (int), ToEmpName (varchar), TopsId (int)

**tblPacketIssue** (5,546,849 rows)
_Records of packets issued out to workers/processes._
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Packet_ID (int), PacketNo (int), SubPcs (varchar), ManagerId (int), ManagerName (varchar), EmpId (int), EmpName (varchar), Process (varchar), Shape (varchar), Purity (varchar), Color (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), PolishedWt (decimal), Value (money), IssueWt (decimal), IssueTime (smalldatetime), UserId (int), UserName (varchar)

**tblPacketPoint** (240,901 rows)
_Weight (in points) of packets._
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Packet_ID (int), PacketNo (int), MarkerId (int), MfgId (int), RMMPoint (decimal), MarkerPoint (decimal), MFGPoint (decimal), FMFGPoint (decimal), ScopePoint (decimal), PolishPoint (decimal), GIAPoint (decimal), DDPoint (decimal), ProcessDate (smalldatetime), Parent_ID (int), FMarkerPoint (decimal), HLMPoint (decimal), FHLMPoint (decimal), MKBPoint (decimal), FMKBPoint (decimal), FScopePoint (decimal), IsRateNotFound (bit)

**tblIssuedPacketDetail** (225,625 rows)
_Detail lines for issued packets._
Columns: ID (int), PacketID (int), EmpID (int), IsFresh (bit), CreatedDate (smalldatetime)

**tblJangadPackets** (190,201 rows)
_Packets sent out on jangad (approval / sale-or-return). IsReceived=0 means still OUT ('currently on jangad'); IsReceived=1 means returned/received. To count packets CURRENTLY on jangad, filter WHERE IsReceived = 0._
Columns: ID (int), JangadId (int), PacketId (int), PacketNo (int), SubPcs (varchar), Carat (decimal), Amount (decimal), IsReceived (bit), RecJangadId (int), Tag (nvarchar)

**tblFinalPacket** (171,765 rows)
_Finished/completed packets._
Columns: ID (int), KapanID (int), KapanName (varchar), PacketID (int), PacketNo (int), SubPcs (varchar), Shape (varchar), Color (varchar), Purity (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florocent (varchar), RoughWt (decimal), CurrentWt (decimal), WeightLoss (decimal), Tops (decimal), Amount (decimal), CreateDate (smalldatetime), UserID (int), Comment (varchar), Lab (varchar)

**tblPacketDetail** (171,112 rows)
_Detailed line items for a packet._
Columns: ID (int), PacketID (int), KetToSymbols (varchar), PolishFeatures (varchar), SymmetryFeatures (varchar), ReportNo (varchar), ColorDescription (varchar), ClarityStatus (varchar), FloroColor (varchar), Girdle (varchar), DepthPer (decimal), TablePer (decimal), CrAng (decimal), CrHt (decimal), PavAng (decimal), PavDp (decimal), StrLn (decimal), LrHalf (decimal), Painting (varchar), Proportion (varchar), ReportComment (varchar), GirdlePer (decimal), Inscription (varchar), SendDate (smalldatetime), Lab (varchar), Height (decimal), MinDia (decimal), MaxDia (decimal)

**tblPacket** (164,573 rows)
_Master list of packets (the central packet record other tables link to)._
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Parent_ID (int), ParentName (varchar), PacketNo (int), SubPcs (varchar), Pcs (int), Shape (varchar), Purity (varchar), Color (varchar), BaseColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), MColor (varchar), MFlorecent (varchar), MCIntencity (int), Depth (decimal), Ratio (decimal), PolishedWt (decimal), RoughWt (decimal), EstWeight (decimal), CurrentWt (decimal), Tension (int), Priority (int), RFID (varchar), PCarat (decimal), RoughValue (decimal), REstimate (money), PAmount (money), Rate (decimal), Discount (decimal), Estimate (money), OEstimate (money), IsOnHold (bit), IsRejected (bit), HasPMFile (bit), HasQCFile (bit), CreDate (smalldatetime), FifoDate (smalldatetime), GQCId (int), RestId (int), CheckerId (int), ManagerId (int), ManagerName (varchar), MBXId (int), LSOId (int), BLKEmpId (int), MFGEmpId (int), PlsEmpId (int), DepartMentId (int), EmpId (int), EmpName (varchar), RunningProcess (varchar), ProcessStartTime (smalldatetime), WeightLoss (decimal), JunkLoss (decimal), UserId (int), UserName (varchar), IsInTempStock (bit), IsOnMemo (bit), MKBWt (decimal), MKBDt (smalldatetime), Lab (varchar), IsRepair (bit), ChildWt (decimal), PolishDate (smalldatetime), OrderNo (int), HasHLMParam (bit)

**tblPacketParameters** (147,636 rows)
Columns: ID (int), PacketID (int), DiaAvg (decimal), DiaMin (decimal), DiaMax (decimal), Depthmm (decimal), Symmetry (varchar), GirdlePer (decimal), DepthPer (decimal), TablePer (decimal), CrAng (decimal), CrHtPer (decimal), PavAng (decimal), PavDpPer (decimal), StrLn (decimal), LrHalf (decimal), Girdle (varchar), GIA (varchar), IGI (varchar), AGS (varchar), HRD (varchar), Ratio (decimal), Comment (varchar), CreatedBy (int), CreatedOn (smalldatetime), Luster (varchar), Graning (varchar), HNA (varchar), EyeClean (varchar), Natural (varchar), ExtraFacetCrown (varchar), ExtraFacetPavilion (varchar), Tinge (varchar), NGTC (varchar), StarAng (decimal), UpAng (decimal), GirdleBzel (varchar), Culet (varchar), CrnPaintAvg (decimal), PavPaintAvg (decimal), TblOffset (decimal), CuletOff (decimal), Allignment (decimal), Tev (decimal), PBCut (varchar), IsSendToLab (bit)

**tblPacketCode** (138,918 rows)
Columns: ID (int), Packet_ID (int), Pcs (int), Code (int), Color (varchar), Tantion (int), Weight (decimal), UserId (int), UserName (varchar), Remark (varchar), MColor (varchar), MFlor (varchar), MCIntencity (int), FL (nvarchar)

**tblPacketPointGIA** (75,712 rows)
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Packet_ID (int), PacketNo (int), MarkerId (int), MfgId (int), RMMPoint (decimal), MarkerPoint (decimal), MFGPoint (decimal), ScopePoint (decimal), PolishPoint (decimal), GIAPoint (decimal), ProcessDate (smalldatetime), Parent_ID (int), FMarkerPoint (decimal), HLMPoint (decimal), FHLMPoint (decimal), MKBPoint (decimal), FMKBPoint (decimal), FScopePoint (decimal), FMFGPoint (decimal), IsRateNotFound (bit), FPolishPoint (decimal)

**tblPacket_BKP** (71,715 rows)
Columns: ID (int), KapanID (int), PacketID (int), ParentID (int), PacketNo (int), RWt (decimal), MkbWt (decimal), PWt (decimal), MRKID (int), MFGID (int), MRKPt (decimal), MFGPt (decimal), PLSPt (decimal), CreateDate (smalldatetime), MKBDate (smalldatetime), MFGDate (smalldatetime), PLSDate (smalldatetime)

**tblKapanValue** (58,460 rows)
Columns: ID (int), KapanId (int), KapanName (nvarchar), MainPcs (int), Pcs (int), RoughWt (decimal), RSTPcs (int), RSTPoint (decimal), GIAPcs (int), GIAPoint (decimal), CreatedAt (smalldatetime)

**tblPacketPrint** (31,858 rows)
Columns: ID (int), PacketID (int), PrintCount (int), ExtraPrint (int), UpdatedBy (int), UpdatedOn (smalldatetime)

**tblPacketOwener** (25,722 rows)
Columns: ID (int), Packet_ID (int), Est_ID (int), Checker_ID (int), Marker_ID (int), Mbox_ID (int), Gqc_ID (int), Mfg_ID (int), Scope_ID (int), Polish_ID (int), DD_ID (int)

**tblStockIssueDetail** (16,210 rows)
Columns: ID (int), ParentId (int), BillId (int), ItemId (int), UnitId (int), Rate (decimal), Quantity (float), Amount (decimal)

**tblStockIssue** (15,947 rows)
Columns: ID (int), EmployeeId (int), StockId (int), TotalAmount (decimal), IssueDate (smalldatetime), IssuedBy (int)

**tblIssuedPacket** (1,585 rows)
Columns: ID (int), EmpId (int), PctIssued (int), CheckIssued (int), IsLastCheck (bit), EntryDate (smalldatetime)

**tblIssuedKapan** (1,365 rows)
Columns: ID (int), DepId (int), DepName (varchar), KapanId (int), KapanName (varchar)

**tblPacketPrintAdditional** (918 rows)
Columns: ID (int), PacketID (int), ExtraPrint (int), UpdatedBy (int), UpdatedOn (smalldatetime)

**tblKapan** (847 rows)
Columns: ID (int), Company_ID (int), KapanName (varchar), Weight (decimal), TotalPcs (int), AvgSize (decimal), Article (varchar), InternalName (varchar), Remark (varchar), IsOnHold (bit), IsFinished (bit), RoughValue (money), EstValue (money), FPoint (money), Labour (decimal), PriorityId (int), CreatDate (smalldatetime), UserId (int), UserName (varchar), BoxId (int), FinishDate (smalldatetime), BoilLoss (decimal), ChapkaLoss (decimal), IsMakeable (bit), InvoiceNo (varchar), JAmount (decimal), DollarRate (decimal), IsRateUpdate (bit), RequireRoughEst (bit), RefId (int), Mine (varchar), Size (varchar), LabourGrade (varchar), AdminId (int), AdminCode (varchar), SuperAdminId (int), SuperAdminCode (varchar), IsFileDelete (bit), DifferWeight (decimal), CleavingDepName (varchar), CleavingDepId (int), RoughOrigin (varchar), CheckerIds (varchar), HasPhoto (bit), CompareKapans (varchar), CheckerCodes (varchar), DbUpdateStopDate (smalldatetime)

**tblKapanChallan** (822 rows)
Columns: ID (int), KapanName (varchar), ChallanNo (int), UpdateDate (smalldatetime)

**tblKtdPacket** (728 rows)
Columns: ID (int), Koted_ID (int), KotedName (varchar), IssueWt (decimal), RecivetWt (decimal), WeightLoss (decimal), CreDate (smalldatetime), EmpID (int), EmpName (varchar), RunningProcess (varchar), UserID (int), UserName (varchar), IsFinish (bit)

**tblTestGXKapanPricePlanMaster** (477 rows)
Columns: ID (int), KapanId (int), Packet_ID (int), PacketName (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), SecColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Tantion (int), PolishedWt (decimal), RoughWt (decimal), Rate (decimal), SecRate (decimal), Discount (decimal), SecDiscount (decimal), Amount (money), SecAmount (money), OAmount (money), SecOAmount (money), PCAvg (decimal), Remark (varchar), RapVer (varchar), IsApproved (bit), IsVerified (bit), IsDamagePlan (bit), HasPlanFile (bit), EmpId (int), EmpName (varchar), EmpCode (varchar), UserId (int), UserName (varchar), CreatDate (smalldatetime), ApproveDate (smalldatetime), Brown (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), Shade (varchar), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), ApproveBy (varchar), Diameter (varchar), TablePer (varchar), CrAng (varchar), PavAng (varchar), Type (varchar), Reason (varchar), RedSpot (varchar), ChipCavity (varchar), CutGrade (varchar), DepthRange (varchar), RatioRange (varchar), TableRange (varchar), OrderNo (int), Height (varchar), TotalDepth (varchar), GirdlePerc (varchar), CrHeight (varchar), PavHeight (varchar), StrLen (varchar), LowHalf (varchar), IsCvd (bit), newDate (smalldatetime)

**tblKapan_BKP** (366 rows)
Columns: ID (int), KapanID (int), KapanName (varchar), CreatedDate (smalldatetime)

**tblTestKapanPricePlanMaster** (184 rows)
Columns: ID (int), KapanId (int), Packet_ID (int), PacketName (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), SecColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Tantion (int), PolishedWt (decimal), RoughWt (decimal), Rate (decimal), SecRate (decimal), Discount (decimal), SecDiscount (decimal), Amount (money), SecAmount (money), OAmount (money), SecOAmount (money), PCAvg (decimal), Remark (varchar), RapVer (varchar), IsApproved (bit), IsVerified (bit), IsDamagePlan (bit), HasPlanFile (bit), EmpId (int), EmpName (varchar), EmpCode (varchar), UserId (int), UserName (varchar), CreatDate (smalldatetime), ApproveDate (smalldatetime), Brown (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), Shade (varchar), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), ApproveBy (varchar), Diameter (varchar), TablePer (varchar), CrAng (varchar), PavAng (varchar), Type (varchar), Reason (varchar), RedSpot (varchar), ChipCavity (varchar), CutGrade (varchar), DepthRange (varchar), RatioRange (varchar), TableRange (varchar), OrderNo (int), Height (varchar), TotalDepth (varchar), GirdlePerc (varchar), CrHeight (varchar), PavHeight (varchar), StrLen (varchar), LowHalf (varchar), IsCvd (bit)

**tblFinalReportSize** (69 rows)
Columns: ID (int), MinWeight (decimal), MaxWeight (decimal), Header (varchar), Param (varchar)

**tblPendingPacketPoint** (8 rows)
Columns: ID (int), PlanId (int), KapanId (int), KapanName (varchar), PacketId (int), PacketNo (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), PolishWt (decimal), Remark (nvarchar), RapVer (varchar), EmpId (int), EmpCode (varchar), CreatDate (smalldatetime), Brown (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), Shade (varchar), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), Diameter (varchar)

**tblConfigIssueSizeRanges** (6 rows)
Columns: ID (int), FromWt (decimal), ToWt (decimal), Percentage (decimal)

**tblChkFinalPoint** (3 rows)
Columns: ID (int), KapanId (int), Kapan (varchar), CheckerId (int), Checker (varchar), FPoint (decimal)

**tblConfigIssueShapeSizes** (2 rows)
Columns: ID (int), FromWt (decimal), ToWt (decimal), Shape (nvarchar), Lab (nvarchar), Amount (decimal)

**tblPacketPointReason** (1 rows)
Columns: ID (int), PacketId (int), KapanName (varchar), PacketNo (int), SubPcs (varchar), Reason (varchar)

**tblBulkPacket** (0 rows)
Columns: ID (int), KapanID (int), KapanName (varchar), Pcs (int), LotNo (int), Weight (decimal), FromDeptId (int), FromDeptName (varchar), FromEmpId (int), FromEmpCode (varchar), Process (varchar), Number (varchar), Shape (varchar), Tops (int), Chapaka (int), IsRejection (bit), LossWt (decimal), ExpPcts (decimal), ExpPctsPercent (decimal), CreatedDate (datetime), DeptId (int), DeptName (varchar), EmpId (int), EmpCode (varchar), RefLotNo (varchar), UserId (int), UserCode (varchar), WtDiffer (decimal), WPerc (decimal)

**tblChkKapanPoint** (0 rows)
Columns: ID (int), Chk (varchar), Kram (varchar), RoughWt (decimal), RoughValue (decimal), RckPoint (decimal), CLVPoint (decimal), DDLPoint (decimal), GIAPoint (decimal), FinPoint (decimal), Article (nvarchar)

**tblKapanPoint** (0 rows)
Columns: ID (int), Kram (varchar), RoughWt (decimal), RoughValue (decimal), CLVPoint (decimal), DDLPoint (decimal), GIAPoint (decimal), FinPoint (decimal), Article (nvarchar)

**tblLotPacketDetail** (0 rows)
Columns: ID (int), TaskId (int), PacketId (int)

**tblPctIssueConfig** (0 rows)
Columns: Id (int), Type (varchar), RapVer (varchar), FromDeptId (int), Dept (varchar), ToDepts (varchar)

**tblPacketColor** (0 rows)
Columns: ID (int), PacketId (int), SerialNo (int), Color (varchar), Comment (varchar), FlCount (int), UserId (int), KapanName (varchar), Code (int)

**tblPacketColorAnalysisTemp** (0 rows)
Columns: ID (int), KapanName (varchar), Code (int), PacketId (int), SerialNo (int), Color (varchar), Comment (varchar), FlCount (int)

**tblPacketGenerateTemp** (0 rows)
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Packet_ID (int), SubPcs (varchar), Pcs (int), Code (int), Color (varchar), BaseColor (varchar), MColor (varchar), MFlorecent (varchar), MCIntencity (int), Florecent (varchar), Tension (int), Weight (decimal), Remark (varchar), UserId (int), UserCode (varchar), DepartMentId (int), DepartmentName (varchar), RFID (varchar), REstimate (money), CreateDate (smalldatetime)

**tblPacketSell** (0 rows)
Columns: ID (int), PacketID (int), RapPrice (decimal), RapValue (decimal), SellDisc (decimal), SellDollar (decimal), SellDate (smalldatetime), Comment (nvarchar), UserID (int), CreatedOn (smalldatetime)

**tblPacketPointGIAReason** (0 rows)
Columns: ID (int), PacketId (int), KapanName (varchar), PacketNo (int), SubPcs (varchar), Reason (varchar)

**tblPacketNumber** (0 rows)
Columns: ID (int), PacketID (int), SrNo (int), PacketName (varchar), Flag (varchar), CreatedOn (smalldatetime)

### Planning & Cutting

**tblPlanMaster** (1,247,480 rows)
_The cutting plan for each rough stone (planning stage)._
Columns: ID (int), KapanId (int), Packet_ID (int), PacketName (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), SecColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Tantion (int), PolishedWt (decimal), RoughWt (decimal), Rate (decimal), SecRate (decimal), Discount (decimal), SecDiscount (decimal), Amount (money), SecAmount (money), OAmount (money), SecOAmount (money), PCAvg (decimal), Remark (varchar), RapVer (varchar), IsApproved (bit), IsVerified (bit), IsDamagePlan (bit), HasPlanFile (bit), EmpId (int), EmpName (varchar), EmpCode (varchar), UserId (int), UserName (varchar), CreatDate (smalldatetime), ApproveDate (smalldatetime), Brown (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), Shade (varchar), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), ApproveBy (varchar), Diameter (varchar), TablePer (varchar), CrAng (varchar), PavAng (varchar), Type (varchar), Reason (varchar), RedSpot (varchar), ChipCavity (varchar), CutGrade (varchar), DepthRange (varchar), RatioRange (varchar), TableRange (varchar), OrderNo (int), Height (varchar), TotalDepth (varchar), GirdlePerc (varchar), CrHeight (varchar), PavHeight (varchar), StrLen (varchar), LowHalf (varchar), IsCvd (bit), IsOrderPlanChecked (bit)

**tblPlanMasterOptional** (701,089 rows)
_Optional/alternative cutting plans for a stone._
Columns: ID (int), KapanId (int), Packet_ID (int), SolNo (int), Shape (varchar), Purity (varchar), Color (varchar), SecColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Tantion (int), PolishedWt (decimal), Rate (decimal), SecRate (decimal), Discount (decimal), SecDiscount (decimal), Amount (money), SecAmount (money), OAmount (money), SecOAmount (money), RapVer (varchar), EmpId (int), EmpCode (varchar), CreatDate (smalldatetime), Brown (varchar), Shade (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), Diameter (varchar), TablePer (varchar), CrAng (varchar), PavAng (varchar), Type (varchar), RedSpot (varchar), ChipCavity (varchar), CutGrade (varchar), DepthRange (varchar), RatioRange (varchar), TableRange (varchar), Height (varchar), TotalDepth (varchar), GirdlePerc (varchar), CrHeight (varchar), PavHeight (varchar), StrLen (varchar), LowHalf (varchar), IsCvd (bit)

**tblPlanReport** (100,119 rows)
Columns: ID (int), DeptID (int), EmpID (int), CreatedByEmpID (int), KapanID (int), KapanName (varchar), PacketID (int), PacketNo (int), SubPcs (varchar), PrePlanID (int), NewPlanID (int), Points (decimal), Rate (decimal), Amount (decimal), IsDamageReport (bit), IsApproved (bit), IsPending (bit), IsHolted (bit), Description (varchar), CreatedDate (smalldatetime), PendingReason (varchar), IsAutoClear (bit), DamageTypeId (int), DamageTypeName (varchar), IsDeductBonus (bit), PlanIds (varchar), PreValue (decimal), NewValue (decimal), PreWt (decimal), NewWt (decimal), WtDiff (decimal), ClearDate (smalldatetime), InceDamageTypeName (varchar)

**tblPlanMaster_Update** (22,307 rows)
Columns: ID (int), PlanID (int), KapanId (int), Packet_ID (int), PacketName (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), SecColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Tantion (int), PolishedWt (decimal), RoughWt (decimal), Rate (decimal), SecRate (decimal), Discount (decimal), SecDiscount (decimal), Amount (money), SecAmount (money), OAmount (money), SecOAmount (money), PCAvg (decimal), Remark (nvarchar), RapVer (varchar), IsApproved (bit), IsVerified (bit), IsDamagePlan (bit), HasPlanFile (bit), EmpId (int), EmpName (varchar), EmpCode (varchar), UserId (int), UserName (varchar), CreatDate (smalldatetime), ApproveDate (smalldatetime), Brown (varchar), Shade (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), UpdateDate (smalldatetime), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), TablePer (decimal), CrAng (decimal), PavAng (decimal), Type (varchar), Diameter (decimal), RedSpot (varchar), ChipCavity (varchar), CutGrade (varchar)

**tblPlanReport_BKP** (2,712 rows)
Columns: ID (int), PacketID (int), EmpID (int), Points (decimal), Comment (varchar), IsDamageReport (bit), OShape (varchar), OPurity (varchar), OColor (varchar), OWt (decimal), OCut (varchar), OPolish (varchar), OSymmetry (varchar), NShape (varchar), NPurity (varchar), NColor (varchar), NWt (decimal), NCut (varchar), NPolish (varchar), NSymmetry (varchar), CreatedDate (smalldatetime)

**tblPlanPoint** (233 rows)
Columns: ID (int), KapanId (int), PacketId (int), EmpId (int), PlanID (int)

**tblPlanParameterMaster** (114 rows)
Columns: ID (int), ParamName (varchar), ParamCode (varchar), ParamValue (varchar), Description (varchar), SortOrder (int), IsActive (bit), ModifiedDate (smalldatetime), ModifiedBy (int), Discount (decimal)

**tblPendingPlan** (85 rows)
Columns: PacketID (int), RapVer (varchar), Reason (varchar)

**tblAllowOrderPlanPermission** (47 rows)
Columns: Id (int), PacketId (int), Flag (bit), CreatedEmpId (int), CreatedDate (smalldatetime)

### Labour & Payroll

**tblLabourRate** (3,379,566 rows)
_Piece-rates paid to labour per process/stage._
Columns: ID (int), CriteriaID (int), FromWt (decimal), ToWt (decimal), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Florocent (varchar), Tantion (int), Amount (decimal), LossAmount (decimal)

**tblBonusRate** (1,535,720 rows)
_Bonus rate definitions used to calculate bonus pay._
Columns: ID (int), CriteriaID (int), FromWt (decimal), ToWt (decimal), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Florocent (varchar), Tantion (int), Amount (decimal)

**tblReportRate** (1,535,720 rows)
_Rates used for reporting/valuation._
Columns: ID (int), CriteriaID (int), FromWt (decimal), ToWt (decimal), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Florocent (varchar), Tantion (int), Amount (decimal)

**tblPointRateLabour** (875,383 rows)
_Labour rate paid per point of weight._
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Department_ID (int), DepartmentName (varchar), Emp_ID (int), EmpName (varchar), Packet_ID (int), PacketNo (int), SubPcs (varchar), Shape (varchar), Tansion (int), Weight (decimal), LossWeight (decimal), Value (decimal), LabourAmount (decimal), LossAmount (decimal), DamageAmount (decimal), ReportPoint (decimal), ReportRate (decimal), ReportAmount (decimal), BonusPoint (decimal), BonusRate (decimal), BonusAmount (decimal), Diff (decimal), FinalLabour (decimal), IsReportLabour (bit), ProcessDate (smalldatetime), CreatedDate (smalldatetime)

**tblLabourResult** (623,404 rows)
_Output/results of labour processing per worker._
Columns: ID (int), Kapan_ID (int), KapanName (varchar), DepartMent_ID (int), DepartMentName (varchar), Emp_ID (int), EmpName (varchar), Packet_ID (int), PacketNo (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), Florocent (varchar), Cut (varchar), Tansion (int), Weight (decimal), WeightRate (decimal), WeightAmount (decimal), LossWeight (decimal), LossRate (decimal), LossAmount (decimal), LabourAmount (decimal), DamageAmount (decimal), ReportPoint (decimal), ReportRate (decimal), ReportAmount (decimal), BonusPoints (decimal), BonusRate (decimal), BonusAmount (decimal), EqualRate (decimal), EqualAmount (decimal), StepRate (decimal), StepAmount (decimal), FinalLabour (decimal), IsReportLabour (bit), ProcessDate (smalldatetime), IsManager (bit), CreatedDate (smalldatetime), GradeAmount (decimal)

**tblIncentiveAmount** (604,055 rows)
_Incentive payment amounts earned by workers._
Columns: ID (int), ReportID (int), EmpID (int), EmpCode (varchar), CreditPoints (decimal), Credit (decimal), DebitPoints (decimal), Debit (decimal), TransactID (int), TransactCode (varchar), TransactTime (smalldatetime)

**tblOriginWiseLabour** (123,552 rows)
Columns: Origin (varchar), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), FL (varchar), FromWt (decimal), ToWt (decimal), Amount (decimal)

**tblLabourResultGIA** (121,337 rows)
Columns: ID (int), Kapan_ID (int), KapanName (varchar), DepartMent_ID (int), DepartMentName (varchar), Emp_ID (int), EmpName (varchar), Packet_ID (int), PacketNo (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), Florocent (varchar), Cut (varchar), Tansion (int), Weight (decimal), WeightRate (decimal), WeightAmount (decimal), BonusPoints (decimal), BonusRate (decimal), BonusAmount (decimal), FinalLabour (decimal), ProcessDate (smalldatetime), IsManager (bit), CreatedDate (smalldatetime), GradeAmount (decimal)

**tblLabourResult_Compare** (95,732 rows)
Columns: ID (int), KapanId (int), KapanName (varchar), PacketId (int), PacketNo (int), SubPcs (varchar), DeptId (int), DeptName (varchar), EmpId (int), EmpCode (varchar), Shape (varchar), Weight (decimal), WeightRate (decimal), WeightAmt (decimal), EColor (varchar), GColor (varchar), ColorRate (decimal), ColorIndex (decimal), ColorAmt (decimal), EPurity (varchar), GPurity (varchar), PurityRate (decimal), PurityIndex (decimal), PurityAmt (decimal), ECut (varchar), GCut (varchar), CutRate (decimal), CutIndex (decimal), CutAmt (decimal), EPolish (varchar), GPolish (varchar), PolishRate (decimal), PolishIndex (decimal), PolishAmt (decimal), ESym (varchar), GSym (varchar), SymRate (decimal), SymIndex (decimal), SymAmt (decimal), EFloro (varchar), GFloro (varchar), FloroRate (decimal), FloroIndex (decimal), FloroAmt (decimal), TotalAmt (decimal), Remark (varchar), ProcessDate (smalldatetime), CreateDate (smalldatetime)

**tblEmpGIABonus** (17,304 rows)
Columns: ID (int), PacketID (int), KapanName (varchar), PacketNo (int), MFGEmpID (int), MFgEmpCode (varchar), MFGPlanID (int), MFGPlanDate (smalldatetime), MFGAmount (money), MFGFAmount (money), PLSPlanId (int), PLSEmpCode (varchar), PLSPlanDate (smalldatetime), PLSAmount (money), PLSFAmount (money), GIAId (int), GIAAmount (money), GIADate (smalldatetime), PolishDate (smalldatetime), CreateDate (smalldatetime)

**tblLabourCriteria** (9,149 rows)
Columns: ID (int), LabourConfigID (int), CardDetail (varchar), Comment (varchar)

**tblPointRate** (8,040 rows)
Columns: Id (int), Origin (varchar), Shape (varchar), FromValue (decimal), ToValue (decimal), Labour (decimal), BonusP (decimal), BonusM (decimal), Report (decimal), UserId (int), CreatedDate (smalldatetime), Lab (varchar)

**tblLabourResultEdit** (5,352 rows)
Columns: ID (int), DeptId (int), EmpId (int), Change (decimal), FromDate (smalldatetime), ToDate (smalldatetime), FromWt (decimal), ToWt (decimal), CreateDate (smalldatetime), UserId (int), ChangeType (varchar), SalaryType (varchar)

**tblLabour_MW** (2,561 rows)
Columns: ID (int), DepId (int), DepName (nvarchar), EmpId (int), EmpName (nvarchar), WorkPoint (decimal), Adjust (decimal), Final (decimal), Month (int), Year (int), Notes (nvarchar), IsEdited (bit), DepLimit (decimal), EmpLimit (decimal)

**tblGPSLabour** (506 rows)
Columns: ID (int), EmpId (int), EmpName (varchar), DeptId (int), RefEmpId (int), RefEmpName (varchar), Level (int), LabourPer (decimal), RefLabour (decimal), Labour (decimal), RefBonusP (decimal), BonusPRate (decimal), RefBonusM (decimal), BonusMRate (decimal), Bonus (decimal), FinalLabour (decimal), FromDate (smalldatetime), ToDate (smalldatetime), CreateDate (smalldatetime)

**tblRateGenerator** (177 rows)
Columns: ID (int), DepartmentId (int), Type (varchar), Amount (decimal), LossAmount (decimal), WeightSteps (varchar), PuritySteps (varchar), ColorSteps (varchar), FlSteps (varchar), CpsSteps (varchar), TanSteps (varchar), CreatedAt (date), UpdatedAt (date), Shape (varchar), IsAdmin (bit)

**tblLabourDepConfig** (36 rows)
Columns: ID (int), LabourTypeID (int), LabourTypeName (varchar), DepID (int), DepName (varchar), RapVer (varchar), Shape (bit), Clarity (bit), Color (bit), Cut (bit), Florocent (bit), Tantion (bit), PlanRequire (bit), LabourTransfer (bit), Manager (bit), IsBonus (bit), SalaryOrigin (varchar), SalaryRapVer (varchar), IncFilter (varchar), IsColorFlFilter (bit), IsPerPcsFilter (bit), IsReconsiderFilter (bit), IsReport (bit), IsWaitForFinalPlan (bit), ReportRate (decimal), DamageReportRate (decimal), IsGenerateOriginLabour (bit)

**tblEmpGpsLabourDetail** (34 rows)
Columns: ID (int), DeptId (int), DeptName (varchar), EmpId (int), EmpName (nvarchar), EmpCode (varchar), Count (int), Amount (decimal), CreatedDate (smalldatetime)

**tblPolishCheckerRate** (29 rows)
Columns: Id (int), FromValue (decimal), ToValue (decimal), Rate (decimal), CutDiff (decimal), PolishDiff (decimal), SymDiff (decimal), ClarityDiff (decimal), ColorDiff (decimal)

**tblPointRateLossSlot** (19 rows)
Columns: Id (int), Origin (varchar), FromWeight (decimal), ToWeight (decimal), Value (decimal)

**tblPointRateSlot** (19 rows)
Columns: Id (int), FromValue (decimal), ToValue (decimal), Division (int), Tan0 (decimal), Tan1 (decimal), Tan2 (decimal), Tan3 (decimal), Tan4 (decimal)

**tblPointRateSlotConfig** (15 rows)
Columns: Id (int), Origin (varchar), IsBoth (bit), Shape (varchar), PercFency (decimal), PrSlotItems (varchar), Lab (varchar)

**tblJangadRate** (8 rows)
Columns: ID (int), PartyId (int), PartyName (nvarchar), Process (nvarchar), FromWt (decimal), ToWt (decimal), Amount (decimal), IsPerPcs (bit)

**tblLabourTypeList** (7 rows)
Columns: ID (int), Name (varchar), Description (varchar)

**tblPointRateTansionConfig** (5 rows)
Columns: Id (int), Tansion (int), Value (decimal)

**tblGPSLabourRate** (2 rows)
Columns: ID (int), Origin (varchar), Level (int), Labour (decimal), BonusP (decimal), BonusM (decimal), UpdatedOn (smalldatetime), UpdatedBy (varchar)

**tblRateConfig** (1 rows)
Columns: ID (int), RateServerIP (varchar), RateDivFactor (decimal), RateTermsPer (decimal), RDLabourPerCarat (decimal), FencyLabourPerCarat (decimal)

**tblLabourConfig** (1 rows)
Columns: ID (int), FinalOrigin (varchar), CompareOrigin (varchar)

**tblBonusFormula** (0 rows)
Columns: ID (int), CriteriaID (int), Formula (varchar), Flag (varchar)

**tblBonusRateManager** (0 rows)
Columns: ID (int), CriteriaID (int), FromWt (decimal), ToWt (decimal), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Florocent (varchar), Tantion (int), Amount (decimal)

**tblBulkRate** (0 rows)
Columns: ID (int), DeptId (int), DeptName (varchar), Process (varchar), FromWt (decimal), ToWt (decimal), Amount (decimal), IsPerPcs (bit)

**tblDeptCompareRate** (0 rows)
Columns: Id (int), DeptId (int), FromWt (decimal), ToWt (decimal), PurStepUpDown (decimal), PurStepEqual (decimal), ColStepUpDown (decimal), ColStepEqual (decimal), CutStepUpDown (decimal), CutStepEqual (decimal), PolStepUpDown (decimal), PolStepEqual (decimal), SymStepUpDown (decimal), SymStepEqual (decimal), FloStepUpDown (decimal), FloStepEqual (decimal), CreateDate (smalldatetime)

**tblLabourCostConfig** (0 rows)
Columns: ID (int), Lab (varchar), Type (varchar), FromWt (decimal), ToWt (decimal), Amount (decimal), RatePer (varchar), IsActive (bit), CreatedDate (datetime), UpdatedDate (datetime)

**tblLabourFormula** (0 rows)
Columns: ID (int), CriteriaID (int), Formula (varchar), Flag (varchar)

**tblLabourGrade** (0 rows)
Columns: ID (int), Article (varchar), Size (varchar), Grade (decimal), Origin (varchar)

**tblLabourLimit** (0 rows)
Columns: ID (int), DeptId (int), DeptName (varchar), EmpId (int), EmpCode (varchar), MinLimit (decimal), MaxLimit (decimal), FromASize (decimal), ToASize (decimal), IsEmployee (bit)

**tblLabourRateManager** (0 rows)
Columns: ID (int), CriteriaID (int), FromWt (decimal), ToWt (decimal), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Florocent (varchar), Tantion (int), Amount (decimal), LossAmount (decimal)

**tblLabourResultGIAEdit** (0 rows)
Columns: ID (int), DeptId (int), EmpId (int), Change (decimal), FromDate (smalldatetime), ToDate (smalldatetime), FromWt (decimal), ToWt (decimal), CreateDate (smalldatetime), UserId (int), ChangeType (varchar), SalaryType (varchar)

**tblStaticDepLabour** (0 rows)
Columns: ID (int), DeptID (int), DeptName (varchar), FromWt (decimal), ToWt (decimal), Amount (decimal), IsPerPcs (bit), Pie (decimal), Saw (decimal)

**tblReportRateManager** (0 rows)
Columns: ID (int), CriteriaID (int), FromWt (decimal), ToWt (decimal), Shape (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Florocent (varchar), Tantion (int), Amount (decimal)

### Employees & HR

**tblTimeAttendance** (393,882 rows)
_Worker attendance records._
Columns: ID (int), MachineNo (nvarchar), UserId (nvarchar), Time (datetime), IsSync (bit), EmpId (int)

**tblTimeAttendance_Demo** (45,636 rows)
Columns: ID (int), MachineNo (nvarchar), UserId (nvarchar), Time (datetime), IsSync (bit), EmpId (int)

**tblEmp_SPC_Criteria** (30,625 rows)
Columns: ID (int), CriteriaId (int), PropertyName (nvarchar), PropertyValue (nvarchar), Priority (int)

**tblLeaveReport** (20,066 rows)
Columns: ID (int), DeptID (int), EmpID (int), ApprovedByID (int), LeaveTypeID (int), LeaveDate_From (smalldatetime), LeaveDate_To (smalldatetime), TimeToLeave (time), TimeToArrive (time), IsApproved (bit), Reason (nvarchar), CreatedDate (smalldatetime)

**tblGraderRemark** (4,156 rows)
Columns: ID (int), PacketId (int), Remark (varchar), CreatedDate (smalldatetime)

**tblEmployeeTimeAttandance** (2,926 rows)
Columns: ID (int), Emp_ID (int), EmpName (varchar), ReceiptName (varchar), ReceiptMobileNo (varchar), PassNo (numeric), PassCode (numeric), CreDate (smalldatetime), IsActive (bit), InTime (smalldatetime), OutTime (smalldatetime)

**tblEmployee** (2,412 rows)
_Master employee records: FirstName, MiddleName, LastName, Code, department, join date, active status. The employee ID is its ID column (referenced elsewhere as Emp_ID / EmpId)._
Columns: ID (int), CompanyId (int), DepartMent_ID (int), DepartMentName (varchar), Code (varchar), SSN (varchar), FirstName (varchar), MiddleName (varchar), LastName (varchar), GrandFather (varchar), BirthDate (smalldatetime), OriginType (varchar), MaritalStatus (varchar), CreatDate (smalldatetime), ChangeDate (smalldatetime), IsActive (bit), IsAvailable (bit), IsFixedSalaried (bit), IsManager (bit), JoinDate (smalldatetime), EmpRefId (varchar), IsGPSEnabled (bit)

**tblEmpDetail** (2,411 rows)
_Employee personal details: address (City, State, Country, Address1/2), phone, mobile, email. Links to tblEmployee via Emp_ID. To find employees by city, join tblEmployee.ID = tblEmpDetail.Emp_ID and filter on City._
Columns: ID (int), Emp_ID (int), Phone (varchar), PhoneNative (varchar), Mobile (varchar), MobileNative (varchar), Email (varchar), Address1 (varchar), Address2 (varchar), City (varchar), State (varchar), Country (varchar), Hobby (varchar), PFNumber (varchar), ESIC (varchar), PanNumber (varchar)

**tblEmp_Criteria** (2,124 rows)
Columns: ID (int), EmpId (int), EmpCode (varchar), EmpGroup (varchar), CycleLimit (int), CurrentPacketLimit (int), CheckPacketLimit (int), IssuePacketLimit (int), ToTension (int), FromTension (int), WtPriority (varchar)

**tblEmp_Weight_Criteria** (1,849 rows)
Columns: ID (int), CriteriaId (int), _From (decimal), _To (decimal), Sec_From (decimal), Sec_To (decimal)

**tblEmpReference** (1,378 rows)
Columns: ID (int), EmpRef_ID (int), Emp_ID (int), EmpRefName (varchar), Relation (varchar), SinceKnown (int), IsActive (bit)

**tblEmp_Value_Criteria** (931 rows)
Columns: ID (int), CriteriaId (int), _From (decimal), _To (decimal), Sec_From (decimal), Sec_To (decimal)

**tblEmployeeCount** (524 rows)
Columns: ID (int), Count (int), Date (smalldatetime), CreatedDate (smalldatetime)

**tblEmpNativeAddress** (521 rows)
Columns: ID (int), EmpID (int), Address (varchar), Village (varchar), Taluka (varchar), District (varchar)

**tblRuleTemplateDetail** (173 rows)
Columns: ID (int), TempID (int), RuleID (int), Value (varchar), Param (varchar), Param1 (varchar), Param2 (varchar), Param3 (varchar)

**tblEmpIpAddress** (159 rows)
Columns: ID (int), EmpId (int), EmpCode (varchar), Ip (varchar)

**tblEmpSitArrangement** (56 rows)
Columns: ID (int), EmpId (int), TableNo (int), Lane (varchar), SeatNo (int), CreatedDate (smalldatetime)

**tblPartyEmps** (50 rows)
Columns: ID (int), PartyId (int), DeptId (int), DeptName (varchar), EmpId (int), EmpCode (varchar), EmpName (varchar)

**tblEmpRating** (30 rows)
Columns: ID (int), EmpId (int), EmpCode (varchar), REmpId (int), REmpCode (varchar), WorkPoint (int), BehaviourPoint (int), UpdatedAt (smalldatetime)

**tblRuleTemplate** (3 rows)
Columns: ID (int), Entity (varchar), Name (varchar), CreatedOn (smalldatetime)

**tblEmpGrade** (0 rows)
Columns: ID (int), Emp_ID (int), EmpName (varchar), Grade (varchar), IsTopMost (bit), Point (decimal)

**tblEmpEduInfo** (0 rows)
Columns: ID (int), Emp_ID (int), Qualification (varchar), SchoolCollege (varchar), University (varchar), Grade (varchar), Marks (varchar), Percentage (varchar)

**tblEmpFamilyInfo** (0 rows)
Columns: ID (int), Emp_ID (int), Name (varchar), Relation (varchar), Education (varchar), BirthDate (smalldatetime), Age (int), Occupation (varchar), IsNominee (bit)

**tblEmpConnDept** (0 rows)
Columns: ID (int), EmpId (int), DeptId (int), DeptName (nvarchar)

**tblMachineShift** (0 rows)
Columns: ID (int), MachineId (int), MachineName (nvarchar), MachineCode (nvarchar), DepartmentId (int), DepartmentName (nvarchar), EmpId (int), EmpName (nvarchar), EmpCode (nvarchar), FromDate (smalldatetime), ToDate (smalldatetime), FromTime (time), ToTime (time), CreatedAt (smalldatetime)

**tblEmpWorkExp** (0 rows)
Columns: ID (int), Emp_ID (int), CompneyName (varchar), Post (varchar), TotalExp (tinyint), ManagerName (varchar), LeaveReason (varchar)

**tblEmpShiftDetails** (0 rows)
Columns: ID (int), Emp_ID (int), ShiftStartDate (smalldatetime), ShiftEndDate (smalldatetime), InTime (smalldatetime), OutTime (smalldatetime)

**tblGraderResult** (0 rows)
Columns: ID (int), KapanId (int), KapanName (varchar), PacketID (int), PacketNo (int), SubPcs (varchar), DeptId (int), DeptName (varchar), GraderId (int), GraderName (varchar), Property (varchar), Value (varchar), UserId (int), UserName (varchar), CreatedDate (smalldatetime)

### Quality & Repair

**tblRepairLog** (657,023 rows)
_Records of stones sent for repair/re-polish._
Columns: ID (int), Kapan_ID (int), Packet_ID (int), PacketNo (int), TableName (varchar), User_ID (int), UserName (varchar), Time (smalldatetime), MAC (varchar)

**tblRepairLogNew** (565,829 rows)
_Newer repair/re-polish log (possibly replaces tblRepairLog)._
Columns: ID (int), KapanID (int), PacketID (int), PlanID (int), DeptID (int), EmpID (int), OtherID (int), TableName (varchar), Specification (varchar), Remark (nvarchar), Flag (int), CreatedBy (int), CreatedDate (smalldatetime), MAC (varchar)

**tblJunk** (201,285 rows)
_Rejected/scrap diamond material._
Columns: ID (int), Kapan_ID (int), Packet_ID (int), Weight (decimal), Pcs (int), Pkt (int), Value (money), Grede (varchar), IsRecyleble (bit), Remark (varchar), IsIssed (bit), IssueDate (smalldatetime), CreateDate (smalldatetime), BulkID (int), LotNo (int)

**tblAIColorPrediction** (56,055 rows)
Columns: KapanName (varchar), Mine (varchar), Size (varchar), Article (varchar), RoughOrigin (varchar), MColor (varchar), MFlorecent (varchar), MCIntencity (int), Tension (int), Gia_Color (varchar), Color_Percent (decimal), Predicted_Gia_Color (varchar), Predicted_Gia_Color_Percent (decimal)

**tblRepairCommentVision** (4,363 rows)
Columns: ID (int), RepairComment (varchar), PlanId (int), KapanId (int), Packet_ID (int), PacketName (int), SubPcs (varchar), Shape (varchar), Purity (varchar), Color (varchar), SecColor (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (decimal), Ratio (decimal), Tantion (int), PolishedWt (decimal), RoughWt (decimal), Rate (decimal), SecRate (decimal), Discount (decimal), SecDiscount (decimal), Amount (money), SecAmount (money), OAmount (money), SecOAmount (money), PCAvg (decimal), Remark (varchar), RapVer (varchar), IsApproved (bit), IsVerified (bit), IsDamagePlan (bit), HasPlanFile (bit), EmpId (int), EmpName (varchar), EmpCode (varchar), UserId (int), UserName (varchar), CreatDate (smalldatetime), ApproveDate (smalldatetime), Brown (varchar), Green (varchar), Milky (varchar), SideBlack (varchar), TableBlack (varchar), SideWhite (varchar), TableWhite (varchar), OpenTable (varchar), OpenCrown (varchar), OpenPavilion (varchar), OpenGirdle (varchar), LAB (varchar), Shade (varchar), Natural (varchar), NaturalCrown (varchar), NaturalPavilion (varchar), HNA (varchar), Culet (varchar), EFCrown (varchar), EFPavilion (varchar), EyeClean (varchar), FLColor (varchar), Girdle (varchar), Luster (varchar), Tinge (varchar), GirdleCondition (varchar), Graining (varchar), ApproveBy (varchar), Diameter (varchar), TablePer (varchar), CrAng (varchar), PavAng (varchar), Type (varchar), Reason (varchar), RedSpot (varchar), ChipCavity (varchar), CutGrade (varchar), DepthRange (varchar), RatioRange (varchar), TableRange (varchar), OrderNo (int), Height (varchar), TotalDepth (varchar), GirdlePerc (varchar), CrHeight (varchar), PavHeight (varchar), StrLen (varchar), LowHalf (varchar), IsCvd (bit)

**tblFavouriteReport** (2,222 rows)
Columns: ID (int), EmpID (int), ReportID (int)

**tblCharacterReport** (769 rows)
Columns: ID (int), EmpID (int), CreatedByEmpID (int), ReportTypeID (int), Notes (varchar), Points (decimal), IsApproved (bit), CreatedDate (smalldatetime)

**tblReportItem** (225 rows)
Columns: ReportId (int), ReportGroupId (int), Name (varchar), Description (varchar), SampleReportImage (image), IsActive (bit), HierId (int), ReportPath (varchar), GroupImageUri (varchar), IsFavorite (bit), ServiceRepId (int)

**tblReportDept** (25 rows)
Columns: ID (int), DeptId (int), Type (nvarchar), RefDeptId (int)

**tblReportType** (17 rows)
Columns: ID (int), Description (varchar), Type (varchar), Points (decimal)

**tblReportGroup** (9 rows)
Columns: ReportGroupId (int), Name (varchar), ImageUri (varchar), IsActive (bit), HierId (int)

**tblRepairConfigComment** (8 rows)
Columns: ID (int), Comment (varchar)

**tblDamageReportType** (8 rows)
Columns: ID (int), Name (varchar), Point (decimal), UpdatedBy (nvarchar), UpdatedOn (smalldatetime)

**tblInceDamageReportType** (2 rows)
Columns: ID (int), Type (varchar)

**tblMergeReportDepartment** (0 rows)
Columns: ID (int), DeptId (int), ParentDeptId (int), ChildDeptId (int), ChildDeptName (varchar)

**tblUserReports** (0 rows)
Columns: ID (int), UserId (int), UserName (varchar), ReportId (int), ReportName (varchar), IsFavorite (bit), IsActive (bit)

**tblRejection** (0 rows)
Columns: ID (int), Packet_ID (int), EmpId (int), EmpName (varchar), Weight (decimal), Value (money), ValueLoss (money), DedValue (money), RejType (varchar), RejDates (smalldatetime), BrokenPcs (int), Remark (varchar)

**tblRepairing** (0 rows)
Columns: ID (int), Packet_ID (int), KapanName (varchar), PacketNo (int), Shape (varchar), Purity (varchar), Color (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Florecent (varchar), Depth (varchar), Ratio (varchar), Weight (decimal), Value (decimal), OrigValue (decimal), EmpID (int), EmpName (varchar), DepartMent (varchar), Process (varchar), CreDate (smalldatetime), UserID (int), UserName (varchar), DepartmentId (int), Origin (varchar), Lab (varchar), IsTransfer (bit)

**tblRepairLoss** (0 rows)
Columns: ID (int), Kapan_ID (int), KapanName (varchar), Packet_ID (int), PacketNo (int), JogiLoss (decimal), DDLoss (decimal), ScopeLoss (decimal)

**tblReportFormula** (0 rows)
Columns: ID (int), CriteriaID (int), Formula (varchar), Flag (varchar)

### Jangad & Transfer

**tblJangad** (15,654 rows)
Columns: ID (int), JangadNo (int), JangadDate (datetime), FromParty (nvarchar), ToParty (nvarchar), FromPartyId (int), ToPartyId (int), TransType (varchar), Process (varchar), KapanId (int), KapanName (nvarchar), Pcs (int), Carats (decimal), RejCarats (decimal), LossCarats (decimal), Amount (decimal), RejAmount (decimal), LossAmount (decimal), BranchId (int), JangadStr (nvarchar), ReferenceNo (nvarchar), ParentTransId (int), ThirdPartyNo (int), CreatedDate (datetime), IsReceived (bit), IsSkipJangad (bit), UserId (int), UserCode (varchar)

**tblJangadBranch** (49 rows)
Columns: ID (int), Name (nvarchar)

**tblJangadProcess** (22 rows)
Columns: ID (int), Name (nvarchar), Description (nvarchar), IsActive (bit), Code (varchar)

**tblJangadTag** (2 rows)
Columns: ID (int), Name (varchar)

**tblJangadTransType** (0 rows)
Columns: ID (int), Name (nvarchar)

**tblJangadDetail** (0 rows)
Columns: ID (int), JangadID (int), PacketID (int), Shape (varchar), Color (varchar), Purity (varchar), Cut (varchar), Polish (varchar), Symmetry (varchar), Weight (decimal), ExWt (decimal), Value (decimal), Tag (varchar), Remark (varchar), IsReceived (bit), ReceivedTime (smalldatetime)

**tblJangadMaster** (0 rows)
Columns: ID (int), PartyID (int), Type (varchar), Pcs (int), Weight (decimal), CreatedBy (int), CreatedByName (varchar), CreatedDate (smalldatetime), IsReceived (bit), ReceivedByName (varchar), ReceivedBy (int), ReceivedDate (smalldatetime)

### Parties & Business

**tblCompanySchedule** (8,212 rows)
Columns: ID (int), CompanyID (int), FromDate (smalldatetime), DeptID (int), IsHoliday (bit), StartTime (smalldatetime), EndTime (smalldatetime), Comment (varchar), ToDate (smalldatetime)

**tblDepartMent** (92 rows)
Columns: ID (int), Company_ID (int), Name (varchar), Code (varchar), Address1 (varchar), Address2 (varchar), City (varchar), State (varchar), Country (varchar), Email (varchar), Phone (varchar), Mobile (varchar), OriginType (varchar), HasManager (bit), AdminId (int), AdminCode (varchar), SuperAdminId (int), SuperAdminCode (varchar), IsActive (bit), LeaveEmpId (int), LeaveEmpCode (varchar), Type (varchar)

**tblDeptConfig** (70 rows)
Columns: ID (int), DeptId (int), DeptMfgChkId (int), IsSolApply (bit), IsElecWeight (bit), DepWeightId (int), ShowGIAPlan (bit), IsLeaveEnForced (bit), ShowOrder (bit), DeptPlsChkIds (varchar), IsAutoApprove (bit)

**tblParty** (51 rows)
Columns: ID (int), Name (varchar), Type (varchar), Address (varchar), ANote (varchar), City (varchar), State (varchar), StateCode (varchar), PinCode (int), PAN (varchar), GST (varchar), PhoneNo (varchar), Code (varchar), BranchId (int), empId (int), empCode (varchar), IsOutSideParty (bit), IsActive (bit), IsPktIssueTask (bit)

**tblSupplier** (50 rows)
Columns: ID (int), Name (varchar), Code (varchar), BusinessType (varchar), OwnerName (varchar), Address1 (varchar), Address2 (varchar), City (varchar), State (varchar), Country (varchar), Phone (varchar), Mobile (varchar), TotalAmount (money)

**tblCompanyType** (2 rows)
Columns: CompneyType1 (nvarchar), Description (nvarchar), Created (timestamp)

**tblCompany** (1 rows)
Columns: ID (int), Name (varchar), Code (varchar), CompanyType (varchar), Address1 (varchar), Address2 (varchar), City (varchar), State (varchar), Country (varchar), Email (varchar), Phone (varchar), Mobile (varchar), LotNo (int), CertificateDate (smalldatetime)

### Masters & Config

**tblRuleDetails** (52,904 rows)
Columns: ID (int), RuleID (int), Entity (varchar), Ident (int), Value (varchar), Param (varchar), Param1 (varchar), Param2 (varchar), Param3 (varchar)

**tblUserConfig** (2,040 rows)
Columns: ID (int), EmpID (int), Theme (nvarchar), ImageName (varchar), IsDashboard (bit), IsChildPacket (bit), IsIncOpen (bit), IsJangadKapan (bit), ChartHeight (nvarchar), ApprovePlan (bit), DashBoardSettings (varchar)

**tblGridConfig** (1,994 rows)
Columns: ID (int), EmpID (int), PageName (varchar), GridName (varchar), GridDetail (varchar)

**tblNcGroupConfig** (924 rows)
Columns: ID (int), GroupName (varchar), FromWt (decimal), ToWt (decimal), Lab (varchar), Shapes (varchar), Colors (varchar), Clarities (varchar), Cuts (varchar), Polish (varchar), Symmetries (varchar), Fluorescences (varchar), Priority (int), CreatedDate (smalldatetime), CreatedBy (varchar), UpdatedBy (varchar), UpdatedDate (smalldatetime)

**tblGPSDepConfig** (435 rows)
Columns: ID (int), DepID (int), RefDepID (int), RefDepName (varchar), RefDepOrigin (varchar), UpdatedOn (smalldatetime), UpdatedBy (varchar)

**tblParameterMaster** (154 rows)
Columns: ID (int), Type (varchar), Name (varchar), Code (varchar), DisplayName (varchar), Index (int), IsActive (bit), Order (int), Words (nvarchar), SvgString (nvarchar), ParentShape (varchar)

**tblDep_Criteria** (77 rows)
Columns: ID (int), DepartMentId (int), DepartMentName (varchar), IsGradeApply (bit), IsCycleApply (bit), IsTantionApply (bit), IsWeightApply (bit), IsValueApply (bit), IsShapeApply (bit), IsPurityApply (bit), IsColorApply (bit), IsCPSApply (bit), IsCutApply (bit)

**tblRuleList** (35 rows)
Columns: ID (int), RuleIdentifier (int), Name (varchar), Category (varchar), RepeatFlag (varchar), Action (varchar), Type (varchar), ErrorText (varchar), IsActive (bit)

**tblTaskType** (22 rows)
Columns: ID (int), CompanyId (int), TaskTypeActionId (int), Type (varchar), Description (varchar), DefaultPriorityId (int), IsActive (bit)

**tblTaskTypeAction** (16 rows)
Columns: ID (int), Description (varchar)

**tblRoughOriginMaster** (14 rows)
Columns: Id (int), Name (varchar), Order (int), Remark (varchar)

**tblTAMachine** (6 rows)
Columns: ID (int), MachineNo (int), IPAddress (varchar), Port (int), InOut (varchar), Description (varchar), IsActive (bit)

**tblNotificationType** (5 rows)
Columns: ID (int), Description (varchar)

**tblRejRules** (4 rows)
Columns: ID (int), Rej_Name (varchar), Description (varchar), DisableRules (bit)

**tblSentenceType** (1 rows)
Columns: ID (int), Name (varchar), Description (varchar), IsEdit (bit)

**tblConfig** (1 rows)
Columns: EnableBackup (bit)

**tblAppConfig** (1 rows)
Columns: ID (int), SSRSUrl (nvarchar), SSRSReportPath (nvarchar), SSRSUserName (nvarchar), SSRSPassword (nvarchar), BaseUrl (nvarchar), SubSystem (bit), KapanDash (bit), PacketNoIncrement (int), IsSubPcs (bit), IsSubPcsNumeric (bit), VGMaxHeliumPrint (int), GDMaxHeliumPrint (int), EXMaxHeliumPrint (int), MaxHeliumPrint (int), MaxHeliumPrintUpdatedOn (smalldatetime), MaxHeliumPrintUpdatedBy (int), ComPort (varchar), DefaultCompanyStartTime (smalldatetime), DefaultCompanyEndTime (smalldatetime), OldPacketDays (int), ImageChangePassword (nvarchar), AttendenceServiceUrl (nvarchar), LoggerPath (varchar), KapanDeletePassword (nvarchar), KapanNameFormat (varchar), PricingAPIPath (nvarchar), EnableSecondaryColor (bit), RfIdActive (bit), IsAutoGenerateEmpCode (bit), EmpCodeDigit (int), MinReportPoint (decimal), EnablePricingRequest (bit), PricingRequestAPIPath (varchar), AllowZeroValuePlan (bit), ByPassCycleForModeratePct (bit), MinReportWeight (decimal), TransferPacketLABEmp (bit), ShowCLVNameWithKapan (bit), SendNotificationonGraderPlan (bit), ShowGIAPlanToEmp (bit), PlanPrintType (varchar), CompanyName (varchar), PacketingPassword (varchar), DefaultDepthRatio (bit), ShowGIAPlanToAssessment (bit), LabWtVariation (decimal), IsShowFinishedKapan (bit), RecMultipleJangad (bit), JangadPcsLimit (int), MinReportPerce (decimal), IsSolutionWiseDisAgree (bit), VisionAPIPath (varchar), ShowEmpToChk (bit), IsVisionUpperCase (bit), ShowUserWiseJangad (bit), DeductProdLabour (bit), TransientJangadNo (int), ShowMarkerSitting (bit), SalesUploadApi (varchar), MarkerCyclePerc (int), IsMkbSignRequire (bit), IsStopPctTransfer (bit), HoldShapes (varchar), IsReferenceShow (bit), IsReferenceBonusShow (bit), IsMfgSignRequire (bit), IsReferenceEmployeeShow (bit), ComPort2 (varchar)

**tblBulkConfig** (0 rows)
Columns: ID (int), FromDeptId (int), FromDeptName (varchar), ToDeptId (int), ToDeptName (varchar), LotType (varchar)

**tblConfigPricingRestricts** (0 rows)
Columns: ID (int), Lab (nvarchar), Amount (decimal)

**tblMachineConfig** (0 rows)
Columns: ID (int), Name (nvarchar), Code (nvarchar), Origin (nvarchar), DepartmentId (int), DepartmentName (nvarchar), PurchageDate (smalldatetime), Cost (decimal), Description (nvarchar), CreatedAt (smalldatetime), Pie (decimal), Saw (decimal)

**tblMfgDaysCriteria** (0 rows)
Columns: ID (int), DeptId (int), DeptName (varchar), Days (int)

**tblGradingMaster** (0 rows)
Columns: ID (int), ParamName (nvarchar), ParamCode (nvarchar), ParamValue (nvarchar), Description (nvarchar), SortOrder (int), IsActive (bit), Discount (decimal), ModifiedDate (smalldatetime), ModifiedBy (int)

**tblUserMaster** (0 rows)
Columns: ID (int), CompanyId (int), UserGroup_ID (int), UserGroupName (varchar), DepartMentId (int), DepartMentName (varchar), DepartMent_OriginType (varchar), EmpId (int), EmpName (varchar), UserName (varchar), Password (varchar), Code (varchar), IsAdmin (bit), IsManager (bit), Domain (varchar), UPN (varchar), MachineID (varchar), CreateDate (smalldatetime), ChangeDate (smalldatetime), LastActiveDate (smalldatetime), IsLokedOut (bit), FailedCount (int)

**tblTaskCanceledType** (0 rows)
Columns: ID (int), Type (varchar), Description (varchar)

**tblPrintConfig** (0 rows)
Columns: ID (int), IsEmpShow (bit), Type (varchar), IsPacketShow (bit), IsPrintTime (bit), Detail (varchar), Height (int), Width (int)

### Other

**tblAllowMKBPermission** (111,473 rows)
Columns: Id (int), PacketId (int), EmpId (int), AllowFlag (bit), CreateDate (smalldatetime)

**tblAllowMrkAdminPermission** (108,008 rows)
Columns: Id (int), PacketId (int), CheckerId (int), AllowFlag (bit), CreatedDate (smalldatetime)

**tblDeletedTask** (101,701 rows)
Columns: ID (int), PacketID (int), ToEmpID (int), FromEmpID (int), DeletedByEmpID (int), GeneratedOn (smalldatetime), CreatedOn (smalldatetime)

**tblPctChecker** (94,020 rows)
Columns: ID (int), PacketId (int), Kapan (varchar), PacketNo (int), MfgEmpId (int), MfgEmpCode (varchar), PolishEmpId (int), PolishEmpCode (varchar)

**tblParam** (61,279 rows)
Columns: ID (int), ParamType (varchar), ParamName (varchar), ParamValue (varchar), ParamValue2 (varchar), SortOrder (int), Shape (varchar), Purity (varchar), Cut (varchar), FromWeight (decimal), ToWeight (decimal), Color (varchar), Tantion (varchar), Lab (varchar)

**tblAllowMFGPermission** (32,926 rows)
Columns: Id (int), PacketId (int), EmpId (int), AllowFlag (bit), CreateDate (smalldatetime)

**tblChkImprovement** (17,479 rows)
Columns: Id (int), KapanId (int), KapanName (varchar), PacketId (int), PacketNo (int), SubPcs (varchar), CheckerId (int), CheckerCode (varchar), Amount (decimal)

**tblSmsResponse** (10,208 rows)
Columns: ID (int), EmpId (int), Code (int), Data (varchar), Message (varchar), IsSucceed (bit), Time (smalldatetime)

**tblUserRights** (5,502 rows)
Columns: ID (int), Origin (varchar), Type (varchar), Value (varchar), IsManager (bit), IsEmployee (bit), DeptID (int), EmpID (int)

**tblNcGroupAssigned** (4,698 rows)
Columns: ID (int), PacketId (int), GroupName (varchar), CreatedDate (smalldatetime)

**tblTask** (4,350 rows)
Columns: ID (int), TaskType_ID (int), Category_ID (int), Packet_ID (int), Subject (varchar), Description (varchar), Dep_ID (int), Department (varchar), Emp_ID (int), EmpCode (varchar), CreatedByEmpId (int), CreatedByEmpName (varchar), PriorityId (int), IsOneTimeTask (bit), IsNotifyUser (bit), CreateDate (smalldatetime), RemindDate (smalldatetime), DueDate (smalldatetime), CompletedDate (smalldatetime), IsCancel (bit), IsComplete (bit), Comment (varchar)

**tblPersonMetaData** (2,939 rows)
Columns: ID (int), Employee_ID (int), OriginTypeID (int), Avatar (image), QRCode (image), AvatarFileType (varchar), AvatarIsAnimated (bit), UriString (varchar)

**tblContactMethod** (1,598 rows)
Columns: ContactMethodID (int), ContactMethodTypeId (smallint), OriginTypeID (tinyint), OriginID (int), ContactMethodValue (varchar), IsAtive (bit), Remark (varchar)

**tblStockDetail** (1,041 rows)
Columns: ID (int), StockId (int), BillId (int), IssueDate (smalldatetime), ItemId (int), UnitId (int), Rate (decimal), Quantity (float), Amount (decimal), Issued (float)

**tblStockPurchageDetail** (1,034 rows)
Columns: ID (int), ParentId (int), ItemId (int), UnitId (int), Rate (decimal), Quantity (float), Amount (decimal), Issued (float)

**tblBoxDetail** (921 rows)
Columns: ID (int), BoxId (int), Granner (varchar), Pcs (int), Weight (decimal), Rate (decimal)

**tblPermissionDetail** (898 rows)
Columns: ID (int), PermID (int), EmpID (int), Value (bit), DepartmentOnly (int), Remarks (varchar)

**tblGirdleDetail** (866 rows)
Columns: Id (int), Shape (varchar), Name (varchar), Value1 (decimal), Value2 (decimal)

**tblArticle** (790 rows)
Columns: ID (int), Name (varchar), Description (varchar)

**tblStockPurchage** (661 rows)
Columns: ID (int), BillNo (nvarchar), BillDate (smalldatetime), PartyId (int), StockId (int), TotalAmount (decimal), CreatedDate (smalldatetime)

**tblBox** (539 rows)
Columns: ID (int), BoxNo (varchar), LotNo (varchar), TotalWeight (decimal), TotalPcs (int), AvgSize (decimal), Article (varchar), Remark (varchar), CreatedBy (varchar), CreatedOn (smalldatetime), UpdatedBy (varchar), UpdatedOn (smalldatetime)

**tblDepParaMeter** (525 rows)
Columns: ID (int), DepartMentID (int), DepartMentName (varchar), EmpID (int), Code (varchar), OriginType (varchar), DepRef (int), IsManager (bit), IsManualIssue (bit), IsAutoIssue (bit), IsSingleIssue (bit)

**tblPctAutomation** (463 rows)
Columns: Id (int), DeptId (int), DeptName (varchar), EmpId (int), EmpCode (varchar), Origin (varchar), KapanId (int), KapanName (varchar), PacketId (int), PacketNo (int), CreateDate (smalldatetime)

**tblStockItem** (394 rows)
Columns: ItemId (int), CategoryId (int), ItemName (nvarchar), UnitId (int), TaxFigure (float), Notes (nvarchar)

**tblHemory** (385 rows)
Columns: ID (int), HemoryType (int), EmpID (int), EmpName (varchar), UserID (int), UserName (varchar), IsFinish (bit), CreateDate (smalldatetime), ReceiveDate (smalldatetime), DeptId (int), DeptName (varchar), HemoryNo (int)

**tblStockTally** (302 rows)
Columns: ID (int), EmpId (int), IsStockTallied (bit), HasCanceled (bit), QueriedBy (int), QueryTime (smalldatetime)

**tblCycleParam** (85 rows)
Columns: ID (int), DepartMentId (int), ParamValue (varchar)

**tblPermissionList** (64 rows)
Columns: ID (int), Name (varchar), GroupName (varchar), DisplayName (varchar)

**tblRapVer** (41 rows)
Columns: ID (int), Origin (varchar), RapVer (varchar)

**tblMine** (40 rows)
Columns: ID (int), Name (varchar)

**tblArticleSize** (16 rows)
Columns: ID (int), Size (varchar)

**tblNcGroupName** (15 rows)
Columns: ID (int), Name (nvarchar)

**tblStockUnit** (11 rows)
Columns: UnitId (int), Symbol (varchar), UnitName (varchar), DecimalPlace (int), SubUnitId (int), SubUnitName (nvarchar), Conversion (float)

**tblStockCategory** (9 rows)
Columns: CategoryId (int), Name (nvarchar), Alias (nvarchar), ParentId (int), ParentName (nvarchar)

**tblSentence** (8 rows)
Columns: ID (int), TypeID (int), TypeName (varchar), Message (varchar)

**tblDep_Suggest** (8 rows)
Columns: ID (int), DepId (int), Value_From (decimal), Value_To (decimal)

**tblBuyerName** (8 rows)
Columns: ID (int), FullName (varchar), ShortName (varchar)

**tblwfCategory** (4 rows)
Columns: CategoryId (int), Description (varchar), IsActive (bit)

**tblwfPriority** (4 rows)
Columns: ID (int), Description (varchar), PriorityValue (int), Active (bit)

**tblNotification** (3 rows)
Columns: ID (int), TaskId (int), TaskTypeActionId (int), TaskTypeActionDescription (varchar), NotificationTypeId (int), NotificationTypeDescription (varchar), HierId (int), SrIdent (int), FriendlyText (varchar), DateCreated (smalldatetime), TS (timestamp), HasViewed (bit), Reminder (smalldatetime)

**tblLoginPopupContents** (3 rows)
Columns: ID (int), DepartmentIds (varchar), Content (nvarchar), IsAllDepartments (bit), ImageBase64 (nvarchar), Priority (int), IsActive (bit)

**tblSarineValue** (2 rows)
Columns: ID (int), PacketId (int), KapanName (varchar), PacketNo (int), Shape (varchar), Wt (decimal), PcColor (varchar), PcClarity (varchar), MColor (varchar), MColorDiff (varchar), GIAColor (varchar), MClarity (varchar), MClarityDiff (varchar), GIAClarity (varchar), CreatedDate (smalldatetime)

**tblStockGodown** (1 rows)
Columns: ID (int), Name (nvarchar), Location (nvarchar), OwenerId (int)

**tblKoted** (1 rows)
Columns: ID (int), Name (varchar), RWeight (decimal), CWeight (decimal), WLoss (decimal), Pcs (int), Value (decimal), CreDate (smalldatetime), UserId (int), UserName (varchar)

**tblCompneyOwener** (1 rows)
Columns: ID (int), Company_ID (int), Name (varchar), Address1 (varchar), Address2 (varchar), City (varchar), State (varchar), Country (varchar), Phone (varchar), Mobile (varchar), PanNo (varchar)

**tblAdminPrivilage** (1 rows)
Columns: ID (int), AdminId (int), AdminCode (varchar), Department (varchar), LossApproval (decimal), DamagePoint (decimal), SendToSuperAdmin (bit), SuperAdminId (int), SuperAdminCode (varchar)

**tblAuthentication** (0 rows)
Columns: ID (int), EmpID (int), UserName (varchar), Password (varchar), ModifiedDate (smalldatetime)

**tblBulkNumber** (0 rows)
Columns: ID (int), WSNumber (varchar), IsActive (bit)

**tblBulkProcess** (0 rows)
Columns: ID (int), Origin (varchar), Process (varchar), IsActive (bit)

**tblCvdPrice** (0 rows)
Columns: Id (int), Clarity (varchar), Color (varchar), Cps (varchar), FromWeight (decimal), ToWeight (decimal), Shape (varchar), Amt (decimal), Rap (decimal), Discount (decimal)

**tblNotifyClient** (0 rows)
Columns: ID (int), UserName (varchar), Udid (varchar), Platform (varchar), AzureId (varchar), Handle (varchar)

**tblOrderDisplay** (0 rows)
Columns: ID (int), OrderNo (varchar), Shape (varchar), Size (varchar), Color (varchar), Clarity (varchar), Cut (varchar), Polish (varchar), Sym (varchar), Fluro (varchar), TD (varchar), TA (varchar), CrAngle (varchar), CrHeight (varchar), PavAngle (varchar), PavHeight (varchar), Ratio (varchar), Culet (varchar), CreatedDate (smalldatetime)

**tblOrderDisplayCondition** (0 rows)
Columns: ID (int), OrderDisplayId (int), Condition (nvarchar)

**tblInclusionInventory** (0 rows)
Columns: ID (int), KapanId (int), Kapan (nvarchar), PacketId (int), PacketNo (int), Shade (nvarchar), Milky (nvarchar), Brown (nvarchar), Green (nvarchar), CenterBlack (nvarchar), SideBlack (nvarchar), OpenCrown (nvarchar), OpenTable (nvarchar), OpenGirdle (nvarchar), OpenPavillion (nvarchar), NaturalOnCrown (nvarchar), NaturalOnGirdle (nvarchar), NaturalOnPavillion (nvarchar), EFOC (nvarchar), EFOP (nvarchar), EyeClean (nvarchar), HNA (nvarchar), CuletCondition (nvarchar), GirdleCondition (nvarchar), CenterSideBlack (nvarchar), CenterSideWhite (nvarchar), CenterWhite (nvarchar), ChipCavity (nvarchar), Culet (nvarchar), EFOG (nvarchar), EFOT (nvarchar), KtoS (nvarchar), NaturalOnTable (nvarchar), RedSpot (nvarchar), SideWhite (nvarchar), BowTie (nvarchar), CreatedOn (smalldatetime)

**tblStockInventory** (0 rows)
Columns: ID (int), ItemId (int), UnitId (int), Quantity (float), StockId (int), IssuedQua (float), CreateDate (smalldatetime), CreatedById (int)

**tblStockTallyLog** (0 rows)
Columns: ID (int), DeptID (int), DepName (varchar), UserId (int), UserCode (varchar), CreateDate (smalldatetime)

**tblUserGroup** (0 rows)
Columns: ID (int), CompanyId (int), GroupName (varchar), Description (varchar)

**tblTaskCanceled** (0 rows)
Columns: ID (int), Task_ID (int), EmpId (int), EmpCode (varchar), CancelTypeId (int), CauseType (varchar), CauseDescription (varchar), Description (varchar), CanceleDate (smalldatetime)

**tblTaskReminder** (0 rows)
Columns: ID (int), Task_ID (int), ReminderInMinutes (int)

**tblTwoFactorAuth** (0 rows)
Columns: ID (int), EmpID (int), FPData (image), IsActive (bit)

## Declared foreign-key relationships

- tblCompneyOwener.Company_ID -> tblCompany.ID
- tblDep_Criteria.DepartMentId -> tblDepartMent.ID
- tblDepartMent.Company_ID -> tblCompany.ID
- tblEmp_Criteria.EmpId -> tblEmployee.ID
- tblEmp_SPC_Criteria.CriteriaId -> tblEmp_Criteria.ID
- tblEmp_Value_Criteria.CriteriaId -> tblEmp_Criteria.ID
- tblEmp_Weight_Criteria.CriteriaId -> tblEmp_Criteria.ID
- tblEmpDetail.Emp_ID -> tblEmployee.ID
- tblEmpEduInfo.Emp_ID -> tblEmployee.ID
- tblEmpFamilyInfo.Emp_ID -> tblEmployee.ID
- tblEmpGrade.Emp_ID -> tblEmployee.ID
- tblEmployee.DepartMent_ID -> tblDepartMent.ID
- tblEmpNativeAddress.EmpID -> tblEmployee.ID
- tblEmpReference.Emp_ID -> tblEmployee.ID
- tblEmpWorkExp.Emp_ID -> tblEmployee.ID
- tblJunk.Packet_ID -> tblPacket.ID
- tblKtdPacket.Koted_ID -> tblKoted.ID
- tblPacket.Parent_ID -> tblPacket.ID
- tblPacket.Kapan_ID -> tblKapan.ID
- tblPacketCode.Packet_ID -> tblPacket.ID
- tblPacketIssue.Packet_ID -> tblPacket.ID
- tblPlanMaster.Packet_ID -> tblPacket.ID
- tblRejection.Packet_ID -> tblPacket.ID
- tblRepairCommentVision.Packet_ID -> tblPacket.ID
- tblRepairing.Packet_ID -> tblPacket.ID
- tblReportItem.ReportGroupId -> tblReportGroup.ReportGroupId
- tblStockItem.UnitId -> tblStockUnit.UnitId
- tblStockItem.CategoryId -> tblStockCategory.CategoryId
- tblStockPurchageDetail.ParentId -> tblStockPurchage.ID
- tblTask.TaskType_ID -> tblTaskType.ID
- tblTask.Category_ID -> tblwfCategory.CategoryId
- tblTask.PriorityId -> tblwfPriority.ID
- tblTaskCanceled.Task_ID -> tblTask.ID
- tblTaskCanceled.CancelTypeId -> tblTaskCanceledType.ID
- tblTaskType.TaskTypeActionId -> tblTaskTypeAction.ID
- tblTaskType.DefaultPriorityId -> tblwfPriority.ID
- tblUserGroup.CompanyId -> tblCompany.ID
- tblUserMaster.CompanyId -> tblCompany.ID
- tblUserMaster.UserGroup_ID -> tblUserGroup.ID

## Tips for framing questions

- Counts: 'How many packets / employees / jangad packets ...?'
- Sums: 'Total labour amount / total weight of junk / total final-packet value ...'
- Filters: by City, Shape, Process, IsApproved, IsReceived, date ranges.
- Group-by: 'packets by shape', 'labour amount by employee', 'attendance by month'.
- Joins: 'employees in Surat', 'labour result per employee with their name'.
- Note: employee names are split into FirstName / MiddleName / LastName.