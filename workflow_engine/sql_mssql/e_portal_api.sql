-- Auto-extracted by scripts/extract_legacy_schema.py from MethylPipeline.sql
-- Idempotent incremental deploy (IF OBJECT_ID / CREATE OR ALTER).
-- Do not edit by hand unless also updating the twin under sql_pg/.

CREATE OR ALTER PROCEDURE e_portal.spSessionSetUserId(@uniSessionId VARCHAR(32), @UserId BIGINT)
AS
BEGIN
  DECLARE @LastUpdate DATETIME = (SELECT MAX(StartDate) FROM EPSessions WHERE sqlSessionId = @@SPID);

  UPDATE EPSessions
  SET
    UserId = @UserId
  WHERE (uniSessionId = @uniSessionId) AND (StartDate = @LastUpdate);
END
GO

CREATE OR ALTER PROCEDURE e_portal.spRoleGrant(@NodeId INT, @AppRoleId TINYINT)
AS
BEGIN
  DECLARE @Id INT = @NodeId;

  WHILE @NodeId IS NOT NULL AND (@Id >= 0)
  BEGIN
    IF NOT EXISTS (SELECT * FROM e_portal.AppRole2Node WHERE AppRoleId = @AppRoleId AND NodeId = @Id)
      INSERT INTO e_portal.AppRole2Node(AppRoleId, NodeId)
      VALUES(@AppRoleId, @Id);

    SET @Id = (SELECT ParentId FROM e_portal.NavTree WHERE Id = @Id);
  END;

  DECLARE @ChildrenQty INT = (SELECT COUNT(*) FROM e_portal.NavTree WHERE ParentId = @NodeId);
  SET @Id = -1;
  WHILE @ChildrenQty > 0
  BEGIN
    SET @Id = (SELECT MIN(Id) FROM e_portal.NavTree WHERE ParentId = @NodeId AND Id > @Id);

    EXEC spRoleGrant @Id, @AppRoleId;

    SET @ChildrenQty = @ChildrenQty - 1;
  END;

  RETURN 0;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spRoleDeny(@NodeId INT, @AppRoleId TINYINT)
AS
BEGIN
  DELETE FROM e_portal.AppRole2Node
  WHERE AppRoleId = @AppRoleId AND NodeId = @NodeId;

  DECLARE @ChildrenQty INT = (SELECT COUNT(*) FROM e_portal.NavTree WHERE ParentId = @NodeId);
  DECLARE @Id INT = -1;
  WHILE @ChildrenQty > 0
  BEGIN
    SET @Id = (SELECT MIN(Id) FROM e_portal.NavTree WHERE ParentId = @NodeId AND Id > @Id);

    EXEC e_portal.spRoleDeny @Id, @AppRoleId;

    SET @ChildrenQty = @ChildrenQty - 1;
  END;

  RETURN 0;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spRemoveUserRole (
  @UserId BIGINT,
  @RoleId BIGINT
) AS
BEGIN
  SET NOCOUNT ON;

  DELETE FROM e_portal.UserRoles
  WHERE UserId = @UserId AND RoleId = @RoleId;

  RETURN 0;
END
GO

CREATE OR ALTER PROCEDURE e_portal.spNodeSetName(@ID INTEGER, @Name VARCHAR(128))
AS
BEGIN
  UPDATE e_portal.NavTree
  SET
    Caption = @Name
  WHERE ID = @ID;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spNodeNewChild(@ParentID INTEGER, @ID INTEGER OUTPUT)
AS
BEGIN
  BEGIN TRANSACTION;

  DECLARE @Children INTEGER = (SELECT COUNT(*) FROM e_portal.NavTree WHERE ParentID = @ParentID);

  INSERT INTO e_portal.NavTree(ParentID, Caption, Seq)
  VALUES(@ParentID, 'New Node', @Children + 1);

  SET @ID = SCOPE_IDENTITY();

  COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spNodeMove(@SrcID INTEGER, @DstID INTEGER)
AS
BEGIN
  DECLARE @SrcSeq INTEGER = (SELECT Seq FROM e_portal.NavTree WHERE ID = @SrcID);
  DECLARE @DstSeq INTEGER = (SELECT Seq FROM e_portal.NavTree WHERE ID = @DstID);

  BEGIN TRANSACTION;

  UPDATE e_portal.NavTree
  SET
    Seq = @DstSeq
  WHERE ID = @SrcID;

  UPDATE e_portal.NavTree
  SET
    Seq = @SrcSeq
  WHERE ID = @DstID;

  COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spNodeDelete(@ID INTEGER)
AS
BEGIN
  DECLARE @ParentID INTEGER = (SELECT ParentID FROM e_portal.NavTree WHERE ID = @ID);
  DECLARE @Seq      INTEGER = (SELECT Seq FROM e_portal.NavTree WHERE ID = @ID);

  BEGIN TRANSACTION;

  DELETE FROM e_portal.NavTree
  WHERE ID = @ID;

  UPDATE e_portal.NavTree
  SET
    Seq = Seq - 1
  WHERE ParentID = @ParentID AND Seq > @Seq;

  COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spNodeCutPaste(@SrcID INTEGER, @DstID INTEGER)
AS
BEGIN
  DECLARE @SrcParentID INTEGER = (SELECT ParentID FROM e_portal.NavTree WHERE ID = @SrcID);
  DECLARE @OldSrcSeq   INTEGER = (SELECT Seq FROM e_portal.NavTree WHERE ID = @SrcID);
  DECLARE @NewDstSeq   INTEGER = COALESCE((SELECT MAX(Seq) FROM e_portal.NavTree WHERE ParentID = @DstID), 0) + 1;

  BEGIN TRANSACTION;

  UPDATE e_portal.NavTree
  SET
    ParentID = @DstID,
    Seq = @NewDstSeq
  WHERE ID = @SrcID;

  UPDATE e_portal.NavTree
  SET
    Seq = Seq - 1
  WHERE ParentID = @SrcParentID AND Seq > @OldSrcSeq;

  COMMIT TRANSACTION;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spInsertFromNavTree(@ID SMALLINT)
AS
BEGIN
  INSERT INTO #Tree(ID, ParentID, Caption, Seq, InfoID)
    SELECT * FROM e_portal.NavTree WHERE ID = @ID;

  DECLARE @ChildrenQty SMALLINT = 0;
  DECLARE @ChildID     SMALLINT = NULL;
  DECLARE @Seq         SMALLINT = -1;

  SET @ChildrenQty = (SELECT COUNT(*) FROM e_portal.NavTree WHERE ParentID = @ID);
  WHILE @ChildrenQty > 0
  BEGIN
    SET @Seq = (SELECT MIN(Seq) FROM e_portal.NavTree WHERE ParentID = @ID AND Seq > @Seq);
    SET @ChildID = (SELECT TOP 1 ID FROM e_portal.NavTree WHERE ParentID = @ID AND Seq = @Seq AND ID NOT IN (SELECT ID FROM #Tree));

    EXEC e_portal.spInsertFromNavTree @ChildID;

    SET @ChildrenQty = @ChildrenQty - 1;
  END;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spGetUserNavTree (@UserId BIGINT, @AppRoleId TINYINT)
AS
BEGIN
  CREATE TABLE #Tree
  (
    Idx       INT IDENTITY,
    ID        smallint,
    ParentID  smallint NULL,
    Caption   varchar(50) NOT NULL,
    Seq       smallint NOT NULL,
    InfoID    int NULL
  );

  EXEC e_portal.spInsertFromNavTree 1;

  WITH UserAuthorizedNodes(NodeId) AS
  (
    SELECT
      NodeId
    FROM
      e_portal.AppRole2Node R
      JOIN e_portal.viewUserAllRoles U ON R.AppRoleId = U.RoleId AND U.UserId = @UserId
    WHERE R.AppRoleId = @AppRoleId
  )
  SELECT
    T.ID,
    T.ParentID,
    T.Caption,
    T.Seq,
    T.InfoID
  FROM #Tree T
  WHERE T.ID IN (SELECT NodeID FROM UserAuthorizedNodes)
  ORDER BY T.Idx;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spGetNavTree(@RootID SMALLINT)
AS
BEGIN
  CREATE TABLE #Tree
  (
    ID        smallint,
    ParentID  smallint NULL,
    Caption   varchar(50) NOT NULL,
    Seq       smallint NOT NULL,
    InfoID    int NULL
  );

  EXEC e_portal.spInsertFromNavTree @RootID;

  SELECT ID, ParentID, Caption, Seq, InfoID AS FormID FROM #Tree;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spGetUserRoles (
  @UserId BIGINT
) AS
BEGIN
  SET NOCOUNT ON;

  ;WITH Permissions (UserId, RoleId, Role, Included) AS
  (
    SELECT
      @UserId,
      r.RoleId,
      r.Name AS Role,
      0 AS Included
    FROM
      e_portal.Roles r
    UNION
    SELECT
      ur.UserId,
      arr.RoleId,
      r.Name AS Role,
      1 AS Included
    FROM
      e_portal.UserRoles ur
      JOIN e_portal.Roles r ON ur.RoleId = r.RoleId
      LEFT JOIN e_portal.AppRole2Roles arr ON r.RoleId = arr.RoleId
    WHERE
      ur.UserId = @UserId
  )
  SELECT
    UserId,
    RoleId,
    Role,
    CAST(MAX(Included) AS BIT) AS Included
  FROM
    Permissions
  GROUP BY
    UserId,
    RoleId,
    Role;
END
GO

CREATE OR ALTER PROCEDURE e_portal.spGetUserIdByEmail(@Email varchar(128), @UserId bigint output)
AS
BEGIN
  SET @UserId = (SELECT UserId FROM [e_portal].SyUsers WHERE Email = @Email);
END
GO

CREATE OR ALTER PROCEDURE e_portal.spGetUserAppRoles (@UserId BIGINT)
AS
BEGIN
  SELECT
    U.UserId,
    R.RoleId,
    R.Name AS Role
  FROM
    e_portal.SyUsers U
    JOIN e_portal.UserRoles UR ON UR.UserId = U.UserId
    JOIN e_portal.Roles R ON R.RoleId = UR.RoleId
  WHERE
    U.UserId = @UserId;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spGetSamplesByPatient
  @ID INT
AS
BEGIN
  SET NOCOUNT ON;

  SELECT
    s.ID,
    s.Age,
    s.Height,
    s.Weight
  FROM portal.Samples s
  WHERE s.ID = @ID;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spGetAllPatients
AS
BEGIN
  SET NOCOUNT ON;

  SELECT
    p.ID,
    p.Name,
    p.Sex
  FROM portal.Patients p
  ORDER BY p.ID;
END;
GO

CREATE OR ALTER PROCEDURE e_portal.spAddUserRole (
  @UserId BIGINT,
  @RoleId BIGINT
) AS
BEGIN
  SET NOCOUNT ON;

  INSERT INTO e_portal.UserRoles (UserId, RoleId)
  VALUES (@UserId, @RoleId);

  RETURN 0;
END
GO

