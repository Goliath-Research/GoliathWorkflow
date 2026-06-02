CREATE TABLE Meta.Collections (
  ID INT IDENTITY PRIMARY KEY,
  Name VARCHAR(200) NOT NULL,
  Type CHAR(1) NOT NULL CHECK (Type IN ('S', 'L', 'T')), -- S = Set, L = List, T = Tree
  ItemClassID INT NULL, -- FK to Meta.TClass if items are objects
  ValueType CHAR(1) NOT NULL CHECK (ValueType IN ('S', 'N', 'O')), -- S = String, N = Number, O = Object reference
  CONSTRAINT FK_Collection_ItemClass FOREIGN KEY (ItemClassID) REFERENCES Meta.Classes(ID)
);

CREATE TABLE Meta.CollectionItem (
  ID INT IDENTITY PRIMARY KEY,
  CollectionID INT NOT NULL,
  ParentID INT NULL, -- For hierarchical trees
  Idx INT NULL, -- For ordered lists
  ValueString VARCHAR(MAX) NULL,
  ValueNumber DECIMAL(38, 10) NULL,
  ValueObjectID INT NULL, -- FK to Meta.Objects (or App.Objs) for object references
  
  CONSTRAINT FK_CollectionItem_Collection FOREIGN KEY (CollectionID) REFERENCES Meta.Collections(ID),
  CONSTRAINT FK_CollectionItem_Parent FOREIGN KEY (ParentID) REFERENCES Meta.CollectionItem(ID),
  CONSTRAINT FK_CollectionItem_Object FOREIGN KEY (ValueObjectID) REFERENCES dbo.Objs(ID),
  
  CONSTRAINT CHK_Values_OnlyOne CHECK (
    (ValueString IS NOT NULL AND ValueNumber IS NULL AND ValueObjectID IS NULL) OR
    (ValueString IS NULL AND ValueNumber IS NOT NULL AND ValueObjectID IS NULL) OR
    (ValueString IS NULL AND ValueNumber IS NULL AND ValueObjectID IS NOT NULL)
  )
);
