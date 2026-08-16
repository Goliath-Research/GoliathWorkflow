-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

CREATE OR ALTER FUNCTION Meta.fnGetViewName (@TableName VARCHAR(64))
RETURNS VARCHAR(64)
BEGIN
  RETURN 'V' + @TableName;
END;
GO

CREATE OR ALTER PROCEDURE Meta.spHistoryInsert(@ObjID INT, @EventID TINYINT, @HistoryID INT OUTPUT)
AS 
BEGIN
	INSERT INTO dbo.History (ObjID, EventID)
    VALUES (@ObjID, @EventID);

  SET @HistoryID = SCOPE_IDENTITY();
END
GO

CREATE OR ALTER FUNCTION Meta.GetClassHasHistory(@ClassID INT)
RETURNS BIT
AS
BEGIN
  RETURN (SELECT HasHistory FROM Meta.Classes WHERE ID = @ClassID);
END;
GO

CREATE OR ALTER FUNCTION Meta.fnGetFirstChildClassID (@ClassID int)
RETURNS INT
AS
BEGIN
  DECLARE @ChildClassID INT;

  SELECT
    @ChildClassID = MIN(c.ID)
  FROM Meta.Classes c
  WHERE c.ParentID = @ClassID;

  RETURN @ChildClassID;
END
GO

--
-- The goal of this procedure is to emulate the
-- behavior of CASCADE DELETE
--
CREATE OR ALTER PROCEDURE Meta.spClassDelete(@ClassID INT)
AS
BEGIN
  DECLARE @ChildClassID INT;

  IF @ClassID IS NULL
    RETURN;

  SET @ChildClassID = Meta.fnGetFirstChildClassID(@ClassID);

  WHILE @ChildClassID IS NOT NULL
  BEGIN
    EXEC Meta.spClassDelete @ClassID = @ChildClassID;

    SET @ChildClassID = Meta.fnGetFirstChildClassID(@ClassID);
  END;
END
GO

CREATE OR ALTER FUNCTION Meta.fnGetClassFieldsWithTypes(@ClassID INT)
RETURNS VARCHAR(8000)
AS
BEGIN
  RETURN
  (
    SELECT STRING_AGG(ColumnDeclaration + ',', CHAR(13) + CHAR(10)) WITHIN GROUP (ORDER BY column_id) AS JoinedColumns
    FROM (
      SELECT 
        QUOTENAME(c.name) + ' ' + 
        t.name + 
        CASE 
           WHEN t.name IN ('char', 'varchar', 'nchar', 'nvarchar') 
                THEN '(' + 
                  CASE WHEN c.max_length = -1 
                    THEN 'MAX' 
                    ELSE CAST(
                      CASE WHEN t.name LIKE 'n%' 
                        THEN c.max_length / 2 
                        ELSE c.max_length 
                      END AS VARCHAR(5)
                    ) 
                  END + ')' 
           ELSE '' 
        END +
        CASE 
           WHEN t.name IN ('decimal', 'numeric') 
                THEN '(' + CAST(c.precision AS VARCHAR(5)) + ',' + CAST(c.scale AS VARCHAR(5)) + ')' 
                ELSE '' 
        END +
        CASE WHEN c.is_nullable = 1 THEN ' NULL' ELSE ' NOT NULL' END AS ColumnDeclaration,
        c.column_id
      FROM sys.columns c
      JOIN sys.types t ON c.user_type_id = t.user_type_id
      JOIN sys.tables tbl ON c.object_id = tbl.object_id
      JOIN Meta.Classes m ON tbl.Name = m.TableName
      WHERE m.ID = @ClassID
    ) src
  )
END;
GO

CREATE OR ALTER PROCEDURE Meta.spClassCreateHistorySql (@ClassID INT, @Sql NVARCHAR(4000) OUTPUT)
AS
BEGIN
  SET NOCOUNT ON;
  DECLARE @TableName VARCHAR(64);
  DECLARE @ViewName VARCHAR(64);
  DECLARE @Fields NVARCHAR(4000);

  SET @TableName = (SELECT 'H' + TableName FROM Meta.Classes WHERE ID = @ClassID);
  IF @TableName IS NULL
    THROW 50001, 'Invalid ClassID', 1;

  SET @Fields = [Meta].[fnGetClassFieldsWithTypes](@ClassID);
  SET @Sql = 
    'CREATE TABLE [dbo].[' + @TableName + '] (' +
    'HID INT NOT NULL, ' +
    'EventTime DATETIME NOT NULL DEFAULT GETDATE(), ' +
    ISNULL(@Fields, '') + 
    'CONSTRAINT PK_' + @TableName + '_HID PRIMARY KEY CLUSTERED (HID), ' +
    'CONSTRAINT FK_' + @TableName + '_History_ID FOREIGN KEY (HID) ' +
    'REFERENCES dbo.History(ID) ON DELETE CASCADE)';
END;
GO

CREATE OR ALTER FUNCTION Meta.fnGetClassFields(@ClassID INT)
RETURNS VARCHAR(8000)
AS
BEGIN
  RETURN (
    SELECT STRING_AGG(c.[name], ', ')
    FROM [sys].[columns] AS c
    INNER JOIN [sys].[tables] AS t ON c.[object_id] = t.[object_id]
    INNER JOIN [Meta].[Classes] AS cls ON t.[name] = cls.[TableName]
    WHERE cls.ID = @ClassID
  );
END;
GO

CREATE OR ALTER PROCEDURE Meta.spClassCreateViewSql(@ClassID INT, @Sql NVARCHAR(4000) OUTPUT)
AS
BEGIN
  DECLARE @ParentClassID    INT;
  DECLARE @ParentClassName  VARCHAR(64);
  DECLARE @ParentTableName  VARCHAR(64);
  DECLARE @ParentViewName   VARCHAR(64);
  DECLARE @TableName        VARCHAR(64);
  DECLARE @ViewName         VARCHAR(64);
  DECLARE @ViewFields       VARCHAR(8000);

  SET @ParentClassID   = (SELECT ParentID FROM Meta.Classes WHERE ID = @ClassID);
  SELECT 
    @ParentClassName = Name,
    @ParentTableName = TableName
  FROM Meta.Classes 
  WHERE ID = @ParentClassID;

  SET @ParentViewName  = Meta.fnGetViewName(@ParentTableName);
  SET @TableName = (SELECT TableName FROM Meta.Classes WHERE ID = @ClassID);

  SET @ViewName  = Meta.fnGetViewName(@TableName);
  SET @ViewFields = Meta.fnGetClassFields(@ClassID);

  -- Add to each field the alias of the table
  -- Delete the start of the fields (ID, )
  -- ID,FirstName,MiddleName,LastName
  SET @ViewFields  = REPLACE(@ViewFields, ', ', ', t.');
  -- ID,t.FirstName,t.MiddleName,t.LastName
  SET @ViewFields  = RIGHT(@ViewFields, LEN(@ViewFields) - 3);
  -- t.FirstName,t.MiddleName,t.LastName

  SET @Sql = 
    'CREATE OR ALTER VIEW ' + @ViewName + 
    ' AS ' +  
    'SELECT pv.*, ' + @ViewFields + 
    ' FROM ' + @ParentViewName + ' pv INNER JOIN ' + @TableName + ' t ON t.ID = pv.ID';
END;
GO

CREATE OR ALTER PROCEDURE Meta.spUpdateObject
    @ClassID        int,                    -- Usually the concrete/leaf class ID
    @ID             int,                    -- Existing object ID to update
    @ValuesJson     nvarchar(max),          -- JSON with fields to update (can span multiple levels)
    @ErrorMessage   nvarchar(1000) = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @TranStarted bit = 0;
    IF @@TRANCOUNT = 0
    BEGIN
        BEGIN TRANSACTION;
        SET @TranStarted = 1;
    END

    BEGIN TRY
        -- 1. Basic validation
        IF NOT EXISTS (SELECT 1 FROM dbo.Objs WHERE ID = @ID)
        BEGIN
            RAISERROR('Object with ID %d does not exist.', 16, 1, @ID);
        END

        IF NOT EXISTS (SELECT 1 FROM Meta.Classes WHERE ID = @ClassID)
        BEGIN
            RAISERROR('Class ID %d does not exist.', 16, 1, @ClassID);
        END

        -- 2. Get full inheritance chain (leaf → root)
        DECLARE @Chain TABLE (
            Ordinal     int IDENTITY(1,1),
            ClassID     int,
            ClassName   nvarchar(128),
            TableName   nvarchar(128)
        );

        WITH hierarchy AS
        (
            SELECT ID, Name, COALESCE(TableName, Name) AS TableName, ParentID, 0 AS Lvl
            FROM Meta.Classes 
            WHERE ID = @ClassID
            
            UNION ALL
            
            SELECT c.ID, c.Name, COALESCE(c.TableName, c.Name), c.ParentID, h.Lvl + 1
            FROM Meta.Classes c
            INNER JOIN hierarchy h ON c.ID = h.ParentID
        )
        INSERT INTO @Chain (ClassID, ClassName, TableName)
        SELECT ID, Name, TableName
        FROM hierarchy
        WHERE TableName <> 'Objs'   -- exclude Objs table
        ORDER BY Lvl DESC;   -- deepest (leaf) first → root last

        -- 3. Update each level that has own columns — from leaf to root
        DECLARE 
            @CurClassID   int,
            @CurTable     sysname,
            @sql          nvarchar(max),
            @setClause    nvarchar(max),
            @hasColumns   bit;

        DECLARE cur CURSOR LOCAL FAST_FORWARD FOR
            SELECT ClassID, TableName 
            FROM @Chain
            ORDER BY Ordinal;   -- leaf → root

        OPEN cur;
        FETCH NEXT FROM cur INTO @CurClassID, @CurTable;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            IF @CurTable IS NULL OR @CurTable = ''
            BEGIN
                FETCH NEXT FROM cur INTO @CurClassID, @CurTable;
                CONTINUE;
            END

            -- Build SET clause only for columns that exist in JSON
            SET @setClause = N'';
            SET @hasColumns = 0;

            SELECT 
                @setClause += 
                    CASE 
                        WHEN EXISTS (
                            SELECT 1 
                            FROM OPENJSON(@ValuesJson)
                            WHERE [key] COLLATE SQL_Latin1_General_CP1_CI_AS = c.name
                        )
                        THEN QUOTENAME(c.name) + ' = JSON_VALUE(@ValuesJson, ''$.' + c.name + '''), '
                    END,
                @hasColumns = 1
            FROM sys.columns c
            WHERE c.object_id = OBJECT_ID(QUOTENAME('dbo') + '.' + QUOTENAME(@CurTable))
              AND c.name <> 'ID'
              AND c.is_computed = 0;

            IF @hasColumns = 0 OR @setClause = ''
            BEGIN
                FETCH NEXT FROM cur INTO @CurClassID, @CurTable;
                CONTINUE;
            END

            -- Remove trailing comma
            SET @setClause = LEFT(@setClause, LEN(@setClause) - 1);

            SET @sql = N'
UPDATE dbo.' + QUOTENAME(@CurTable) + N'
SET ' + @setClause + N'
WHERE ID = @ID;';

            -- Debug option (uncomment when developing)
            -- PRINT @sql;

            EXEC sp_executesql 
                @sql,
                N'@ID int, @ValuesJson nvarchar(max)',
                @ID = @ID,
                @ValuesJson = @ValuesJson;

            FETCH NEXT FROM cur INTO @CurClassID, @CurTable;
        END

        CLOSE cur;
        DEALLOCATE cur;

        -- 4. Optional - History entry (if the concrete class tracks history)
        DECLARE @HasHistory bit;
        SELECT @HasHistory = HasHistory 
        FROM Meta.Classes 
        WHERE ID = @ClassID;

        IF @HasHistory = 1
        BEGIN
            INSERT dbo.History (ObjID, EventID, EventTime)
            VALUES (@ID, 2, DEFAULT);  -- 2 = Updated (you may use different EventID)
        END

        IF @TranStarted = 1
            COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @TranStarted = 1 AND XACT_STATE() = -1
            ROLLBACK TRANSACTION;

        SET @ErrorMessage = 
            N'Error in Meta.spUpdateObject (ID=' + CAST(@ID AS nvarchar(20)) + 
            N', ClassID=' + CAST(@ClassID AS nvarchar(20)) + N'): ' +
            ERROR_MESSAGE();

        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE Meta.spObjectInsert(@ClassID INT, @ID INT OUTPUT)
AS 
BEGIN
  IF NOT EXISTS (SELECT * FROM Meta.Classes WHERE ID = @ClassID)
  BEGIN
    SET @ID = NULL;
    RETURN;
  END;

  INSERT INTO dbo.TObject(ClassID)
    VALUES(@ClassID);

  SET @ID = SCOPE_IDENTITY();
END;
GO

CREATE OR ALTER PROCEDURE Meta.spInsertObject
    @ClassID        int,
    @ValuesJson     nvarchar(max),
    @NewID          int           OUTPUT,
    @ErrorMessage   nvarchar(1000) = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @TranStarted bit = 0;
    IF @@TRANCOUNT = 0
    BEGIN
        BEGIN TRANSACTION;
        SET @TranStarted = 1;
    END

    BEGIN TRY
        -- Validate class
        IF NOT EXISTS (SELECT 1 FROM Meta.Classes WHERE ID = @ClassID)
            RAISERROR('Class ID %d not found.', 16, 1, @ClassID);

        -- Build chain leaf → root, exclude Objs
        DECLARE @Chain TABLE (
            Ordinal     int IDENTITY,
            ClassID     int,
            TableName   nvarchar(128)
        );

        ;WITH hierarchy AS (
            SELECT ID, COALESCE(TableName, Name) AS TableName, ParentID, 0 AS Lvl
            FROM Meta.Classes WHERE ID = @ClassID
            UNION ALL
            SELECT c.ID, COALESCE(c.TableName, c.Name), c.ParentID, h.Lvl + 1
            FROM Meta.Classes c INNER JOIN hierarchy h ON c.ID = h.ParentID
        )
        INSERT @Chain (ClassID, TableName)
        SELECT ID, TableName
        FROM hierarchy
        WHERE TableName <> 'Objs'
        ORDER BY Lvl DESC;

        -- Create Objs row
        INSERT dbo.Objs (ClassID) VALUES (@ClassID);
        SET @NewID = SCOPE_IDENTITY();

        IF @NewID IS NULL
            RAISERROR('Failed to insert into Objs.', 16, 1);

        -- Process tables
        DECLARE 
            @CurTable   nvarchar(128),
            @sql        nvarchar(max),
            @cols       nvarchar(max),
            @values     nvarchar(max),
            @setClause  nvarchar(max);

        DECLARE cur CURSOR LOCAL FAST_FORWARD FOR 
            SELECT TableName FROM @Chain;

        OPEN cur;
        FETCH NEXT FROM cur INTO @CurTable;

        WHILE @@FETCH_STATUS = 0
        BEGIN
            IF @CurTable IS NULL OR @CurTable = ''
            BEGIN
                FETCH NEXT FROM cur INTO @CurTable;
                CONTINUE;
            END

            SET @cols = N'';
            SET @values = N'';
            SET @setClause = N'';

            SELECT 
                @cols      += CASE WHEN @cols = '' THEN '' ELSE ', ' END + QUOTENAME(name),
                @values    += CASE WHEN @values = '' THEN '' ELSE ', ' END + 'JSON_VALUE(@ValuesJson, ''$.' + name + ''')',
                @setClause += CASE WHEN @setClause = '' THEN '' ELSE ', ' END + QUOTENAME(name) + ' = JSON_VALUE(@ValuesJson, ''$.' + name + ''')'
            FROM sys.columns
            WHERE object_id = OBJECT_ID('dbo.' + @CurTable)
              AND name <> 'ID'
              AND is_computed = 0;

            IF @cols = ''
            BEGIN
                FETCH NEXT FROM cur INTO @CurTable;
                CONTINUE;
            END

            -- Safe & debug-friendly
            SET @sql = CONCAT(
                N'MERGE dbo.', QUOTENAME(@CurTable), N' AS tgt ',
                N'USING (VALUES (@NewID)) AS src(ID) ',
                N'ON tgt.ID = src.ID ',
                N'WHEN MATCHED THEN ',
                N'    UPDATE SET ', @setClause, N' ',
                N'WHEN NOT MATCHED BY TARGET THEN ',
                N'    INSERT (ID',
                CASE WHEN @cols <> '' THEN CONCAT(N', ', @cols) ELSE N'' END,
                N') ',
                N'VALUES (@NewID',
                CASE WHEN @values <> '' THEN CONCAT(N', ', @values) ELSE N'' END,
                N');'
            );
            
            EXEC sp_executesql 
                @sql,
                N'@NewID int, @ValuesJson nvarchar(max)',
                @NewID      = @NewID,
                @ValuesJson = @ValuesJson;

            FETCH NEXT FROM cur INTO @CurTable;
        END

        CLOSE cur;
        DEALLOCATE cur;

        -- History
        IF EXISTS (SELECT 1 FROM Meta.Classes WHERE ID = @ClassID AND HasHistory = 1)
            INSERT dbo.History (ObjID, EventID, EventTime)
            VALUES (@NewID, 1, DEFAULT);

        IF @TranStarted = 1 
          COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @TranStarted = 1 AND XACT_STATE() = -1 
          ROLLBACK TRANSACTION;
        SET @ErrorMessage = ERROR_MESSAGE();
        THROW;
    END CATCH
END
GO

CREATE OR ALTER PROCEDURE Meta.spClassCreateTableSql(@ClassID INT, @Sql NVARCHAR(4000) OUTPUT)
AS
BEGIN
  DECLARE @TableName VARCHAR(64);
  DECLARE @Fields NVARCHAR(4000);
  SET @TableName = (SELECT TableName FROM Meta.Classes WHERE ID = @ClassID);
  SET @Fields = 
  (
    SELECT 
        STRING_AGG
        (
            f.Name + ' ' + t.Name + CASE WHEN f.IsRequired = 1 THEN ' NOT NULL' ELSE '' END, 
            ', '
        )
    FROM 
        Meta.Fields f
            INNER JOIN Meta.Types t ON f.TypeID = t.ID
    WHERE f.ClassID = @ClassID
  );
  SET @Sql = 
    'CREATE TABLE [dbo].[' + @TableName + '] (' +
    'ID BIGINT NOT NULL, ' + 
    ISNULL(@Fields, '') + ', ' +
    'CONSTRAINT PK_' + @TableName + '_ID PRIMARY KEY CLUSTERED (ID), ' +
    'CONSTRAINT FK_' + @TableName + '_TObject_ID FOREIGN KEY (ID) ' +
    'REFERENCES Meta.TObject (ID) ON DELETE CASCADE)';
END;
GO

-- The goal of this procedure is to automate the
-- creation of the recursive view by creating a
-- new view joining the parent view with the
-- inherited table (that is, all the columns from
-- the parent and the additional columns in the
-- child)
-- If the class includes the definition of the
-- properties, it is also possible to create
-- the columns and their constraints.
CREATE OR ALTER PROCEDURE Meta.spClassAdded (@ClassID INT)
AS
BEGIN
  DECLARE @TableName VARCHAR(64);
  DECLARE @Fields VARCHAR(8000);
  DECLARE @ViewName VARCHAR(64);
  DECLARE @SqlCode NVARCHAR(4000);
  DECLARE @HasHistory BIT;
  DECLARE @HistoryTable VARCHAR(64);

  SELECT
    @TableName = TableName
   ,@HasHistory = HasHistory
  FROM Meta.Classes
  WHERE ID = @ClassID;

  -- If the table is not yet created, create it!
  IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = @TableName)
  BEGIN
    EXEC Meta.spClassCreateTableSql @ClassID = @ClassID, @Sql = @SqlCode OUTPUT;

    EXEC sp_executesql @SqlCode;
  END;

  -- Now we can create the view

  EXEC Meta.spClassCreateViewSql @ClassID = @ClassID, @Sql = @SqlCode OUTPUT;
  EXEC sp_executesql @SqlCode;

  -- If this class will keep a history of its objects, create the history table.
  -- Its structure will be identical as the view, but adding an ID and timestamp.
  IF @HasHistory = 1
  BEGIN
    EXEC Meta.spClassCreateHistorySql @ClassID = @ClassID, @Sql = @SqlCode OUTPUT;

    EXEC sp_executesql @SqlCode;
  END
END
GO

