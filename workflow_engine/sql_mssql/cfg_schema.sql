/*
  Configuration registry schema (science/deploy config — NOT wf engine).
*/
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'cfg')
BEGIN
    EXEC(N'CREATE SCHEMA cfg');
END
GO
