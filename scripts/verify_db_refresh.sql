/*
  verify_db_refresh.sql — run after restoring a new client backup side-by-side.

  Purpose: the bot's accuracy depends on ~23 EMPIRICAL facts about the data that are
  hard-coded in app/schema/glossary.py (known-empty tables, dead columns, dead date
  ranges, identity keys). A newer backup can silently flip any of them, which turns
  correct guidance into confident WRONG answers. This script re-checks them.

  Usage:
    sqlcmd -S localhost -E -i scripts\verify_db_refresh.sql -o outputs\db_refresh_report.txt

  Set OLD/NEW below to the two database names.
*/
SET NOCOUNT ON;
DECLARE @old SYSNAME = N'AasthaErp';       -- previous snapshot
DECLARE @new SYSNAME = N'AasthaErp_new';   -- newly restored backup

PRINT '================ 1. STRUCTURAL DIFF: TABLES ================';
DECLARE @sql NVARCHAR(MAX) = N'
SELECT ''ADDED in new'' AS change_type, t.TABLE_NAME AS table_name
FROM ' + QUOTENAME(@new) + N'.INFORMATION_SCHEMA.TABLES t
WHERE t.TABLE_TYPE = ''BASE TABLE''
  AND NOT EXISTS (SELECT 1 FROM ' + QUOTENAME(@old) + N'.INFORMATION_SCHEMA.TABLES o
                  WHERE o.TABLE_NAME = t.TABLE_NAME AND o.TABLE_TYPE = ''BASE TABLE'')
UNION ALL
SELECT ''DROPPED from new'', o.TABLE_NAME
FROM ' + QUOTENAME(@old) + N'.INFORMATION_SCHEMA.TABLES o
WHERE o.TABLE_TYPE = ''BASE TABLE''
  AND NOT EXISTS (SELECT 1 FROM ' + QUOTENAME(@new) + N'.INFORMATION_SCHEMA.TABLES t
                  WHERE t.TABLE_NAME = o.TABLE_NAME AND t.TABLE_TYPE = ''BASE TABLE'')
ORDER BY 1, 2;';
EXEC sp_executesql @sql;

PRINT '';
PRINT '================ 2. STRUCTURAL DIFF: COLUMNS ================';
SET @sql = N'
SELECT ''ADDED in new'' AS change_type, n.TABLE_NAME AS table_name, n.COLUMN_NAME AS column_name,
       n.DATA_TYPE AS data_type
FROM ' + QUOTENAME(@new) + N'.INFORMATION_SCHEMA.COLUMNS n
WHERE EXISTS (SELECT 1 FROM ' + QUOTENAME(@old) + N'.INFORMATION_SCHEMA.TABLES o
              WHERE o.TABLE_NAME = n.TABLE_NAME AND o.TABLE_TYPE = ''BASE TABLE'')
  AND NOT EXISTS (SELECT 1 FROM ' + QUOTENAME(@old) + N'.INFORMATION_SCHEMA.COLUMNS oc
                  WHERE oc.TABLE_NAME = n.TABLE_NAME AND oc.COLUMN_NAME = n.COLUMN_NAME)
UNION ALL
SELECT ''DROPPED from new'', o.TABLE_NAME, o.COLUMN_NAME, o.DATA_TYPE
FROM ' + QUOTENAME(@old) + N'.INFORMATION_SCHEMA.COLUMNS o
WHERE EXISTS (SELECT 1 FROM ' + QUOTENAME(@new) + N'.INFORMATION_SCHEMA.TABLES t
              WHERE t.TABLE_NAME = o.TABLE_NAME AND t.TABLE_TYPE = ''BASE TABLE'')
  AND NOT EXISTS (SELECT 1 FROM ' + QUOTENAME(@new) + N'.INFORMATION_SCHEMA.COLUMNS nc
                  WHERE nc.TABLE_NAME = o.TABLE_NAME AND nc.COLUMN_NAME = o.COLUMN_NAME)
UNION ALL
SELECT ''TYPE CHANGED'', o.TABLE_NAME, o.COLUMN_NAME,
       o.DATA_TYPE + '' -> '' + nc.DATA_TYPE
FROM ' + QUOTENAME(@old) + N'.INFORMATION_SCHEMA.COLUMNS o
JOIN ' + QUOTENAME(@new) + N'.INFORMATION_SCHEMA.COLUMNS nc
  ON nc.TABLE_NAME = o.TABLE_NAME AND nc.COLUMN_NAME = o.COLUMN_NAME
WHERE o.DATA_TYPE <> nc.DATA_TYPE
ORDER BY 1, 2, 3;';
EXEC sp_executesql @sql;

PRINT '';
PRINT '================ 3. ROW-COUNT DELTA (key tables) ================';
SET @sql = N'
WITH o AS (SELECT t.name AS tbl, SUM(p.rows) AS rows_
           FROM ' + QUOTENAME(@old) + N'.sys.tables t
           JOIN ' + QUOTENAME(@old) + N'.sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
           GROUP BY t.name),
     n AS (SELECT t.name AS tbl, SUM(p.rows) AS rows_
           FROM ' + QUOTENAME(@new) + N'.sys.tables t
           JOIN ' + QUOTENAME(@new) + N'.sys.partitions p ON p.object_id = t.object_id AND p.index_id IN (0,1)
           GROUP BY t.name)
SELECT COALESCE(n.tbl, o.tbl) AS table_name,
       o.rows_ AS old_rows, n.rows_ AS new_rows,
       ISNULL(n.rows_,0) - ISNULL(o.rows_,0) AS delta
FROM o FULL OUTER JOIN n ON n.tbl = o.tbl
WHERE ISNULL(n.rows_,0) <> ISNULL(o.rows_,0)
ORDER BY ABS(ISNULL(n.rows_,0) - ISNULL(o.rows_,0)) DESC;';
EXEC sp_executesql @sql;
