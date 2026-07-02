CREATE PROCEDURE dbo.TransferObjsFromBatches
AS
BEGIN
  SET NOCOUNT ON;

  DECLARE @ObjID INT;
  DECLARE @MetaObjID INT;
  DECLARE @BatchID INT;
  DECLARE @ClassBatches INT;

  SET @ClassBatches = (SELECT ID FROM Meta.Classes WHERE Name = 'Batch');

  DECLARE batch_cursor CURSOR FOR
    SELECT ID FROM portal.Batches;

  OPEN batch_cursor;
  FETCH NEXT FROM batch_cursor INTO @ObjID;

  WHILE @@FETCH_STATUS = 0
  BEGIN
    -- Insert into Meta.Objs with fixed ClassID = 5, returning identity
    INSERT INTO Meta.Objs (ClassID)
    VALUES (@ClassBatches);

    SET @MetaObjID = SCOPE_IDENTITY();

    -- Insert into portal.Objs with ObjID from batch and identity from Meta.Objs insert
    INSERT INTO portal.Objs (ObjID, MetaObjID)
    VALUES (@ObjID, @MetaObjID);

    FETCH NEXT FROM batch_cursor INTO @ObjID;
  END;

  CLOSE batch_cursor;
  DEALLOCATE batch_cursor;
END
