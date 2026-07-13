/*
  Align cfg JSON payload columns to native Azure SQL json.
  Safe to re-run: skips columns already typed as json.
  Fixes earlier mistaken nvarchar(max) storage (db_objects contract).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

DECLARE @sql nvarchar(max);

DECLARE col_cur CURSOR LOCAL FAST_FORWARD FOR
SELECT
    N'ALTER TABLE ' + QUOTENAME(OBJECT_SCHEMA_NAME(c.object_id)) + N'.'
      + QUOTENAME(OBJECT_NAME(c.object_id))
      + N' ALTER COLUMN ' + QUOTENAME(c.name) + N' json '
      + CASE WHEN c.is_nullable = 1 THEN N'NULL' ELSE N'NOT NULL' END + N';'
FROM sys.columns AS c
INNER JOIN sys.types AS t ON t.user_type_id = c.user_type_id
INNER JOIN sys.tables AS tb ON tb.object_id = c.object_id
INNER JOIN sys.schemas AS s ON s.schema_id = tb.schema_id
WHERE s.name = N'cfg'
  AND c.name IN (
      N'document_json',
      N'secret_json',
      N'location_json'
  )
  AND t.name <> N'json';

OPEN col_cur;
FETCH NEXT FROM col_cur INTO @sql;
WHILE @@FETCH_STATUS = 0
BEGIN
    PRINT @sql;
    EXEC sys.sp_executesql @sql;
    FETCH NEXT FROM col_cur INTO @sql;
END
CLOSE col_cur;
DEALLOCATE col_cur;
GO
