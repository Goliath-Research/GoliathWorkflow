unit SchemaCatalog;

interface

uses
  SchemaDocument,
  SchemaDocumentCache,
  SchemaNode,
  Spring.Collections,
  System.SysUtils;

type
  TSchemaCatalogEntry = record
    DisplayName: string;
    FilePath: string;
  end;

  TSchemaCatalog = class
  private
    class var FCurrent: TSchemaCatalog;
    FEntries: IList<TSchemaCatalogEntry>;
    FDocuments: TSchemaDocumentCache;
    class function CanonicalName(const Value: string): string; static;
    class function EntrySchemaName(const Entry: TSchemaCatalogEntry): string; static;
    procedure ScanDirectory(const Root: string; const Relative: string);
    function TryLoadDocument(Index: Integer; out Document: TSchemaDocument): Boolean;
  public
    constructor Create;
    destructor Destroy; override;
    class function Current: TSchemaCatalog; static;
    class procedure SetCurrent(ACatalog: TSchemaCatalog); static;
    procedure LoadFromRoot(const SchemasRoot: string);
    function Count: Integer;
    function Entry(Index: Integer): TSchemaCatalogEntry;
    function FindByPath(const Path: string): Integer;
    function FindByName(const Name: string): Integer;
    function TryResolveSchema(const Name: string; out Node: TSchemaNode): Boolean;
    function TryGetDocument(const Path: string; out Document: TSchemaDocument): Boolean;
    procedure PutDocument(const Path: string; ADocument: TSchemaDocument);
  end;

implementation

uses
  JsonSchemaLoader,
  System.IOUtils,
  System.StrUtils;

constructor TSchemaCatalog.Create;
begin
  inherited Create;
  FEntries := TCollections.CreateList<TSchemaCatalogEntry>;
  FDocuments := TSchemaDocumentCache.Create;
end;

destructor TSchemaCatalog.Destroy;
begin
  if FCurrent = Self then
    FCurrent := nil;
  FDocuments.Free;
  FDocuments := nil;
  inherited Destroy;
end;

class function TSchemaCatalog.Current: TSchemaCatalog;
begin
  Result := FCurrent;
end;

class procedure TSchemaCatalog.SetCurrent(ACatalog: TSchemaCatalog);
begin
  FCurrent := ACatalog;
end;

class function TSchemaCatalog.CanonicalName(const Value: string): string;
var
  Ch: Char;
  S: string;
begin
  S := LowerCase(Trim(Value));
  Result := '';
  for Ch in S do
    if CharInSet(Ch, ['a'..'z', '0'..'9']) then
      Result := Result + Ch;
end;

class function TSchemaCatalog.EntrySchemaName(
  const Entry: TSchemaCatalogEntry): string;
begin
  Result := TPath.GetFileName(Entry.FilePath);
  if EndsText('.schema.json', Result) then
    Delete(Result, Length(Result) - Length('.schema.json') + 1, MaxInt)
  else if EndsText('.json', Result) then
    Delete(Result, Length(Result) - Length('.json') + 1, MaxInt)
  else if EndsText('.schema', Result) then
    Delete(Result, Length(Result) - Length('.schema') + 1, MaxInt);
end;

procedure TSchemaCatalog.ScanDirectory(const Root, Relative: string);
var
  FullDir: string;
  FileName: string;
  Entry: TSchemaCatalogEntry;
  RelPath: string;
begin
  FullDir := Root;
  if Relative <> '' then
    FullDir := TPath.Combine(Root, Relative);
  if not TDirectory.Exists(FullDir) then
    Exit;
  for FileName in TDirectory.GetFiles(FullDir, '*.schema.json', TSearchOption.soTopDirectoryOnly) do
  begin
    Entry.FilePath := FileName;
    RelPath := FileName;
    if Relative <> '' then
      Entry.DisplayName := Relative + '/' + TPath.GetFileName(FileName)
    else
      Entry.DisplayName := TPath.GetFileName(FileName);
    FEntries.Add(Entry);
  end;
  for FileName in TDirectory.GetDirectories(FullDir) do
  begin
    if Relative = '' then
      ScanDirectory(Root, TPath.GetFileName(FileName))
    else
      ScanDirectory(Root, Relative + '/' + TPath.GetFileName(FileName));
  end;
end;

procedure TSchemaCatalog.LoadFromRoot(const SchemasRoot: string);
begin
  FEntries.Clear;
  FDocuments.Clear;
  ScanDirectory(SchemasRoot, '');
  FEntries.Sort(
    function(const Left, Right: TSchemaCatalogEntry): Integer
    begin
      Result := CompareText(Left.DisplayName, Right.DisplayName);
    end);
end;

function TSchemaCatalog.TryGetDocument(const Path: string;
  out Document: TSchemaDocument): Boolean;
begin
  Result := FDocuments.TryGet(Path, Document);
end;

procedure TSchemaCatalog.PutDocument(const Path: string;
  ADocument: TSchemaDocument);
begin
  FDocuments.Add(Path, ADocument);
end;

function TSchemaCatalog.TryLoadDocument(Index: Integer;
  out Document: TSchemaDocument): Boolean;
var
  Loader: TJsonSchemaLoader;
  Path: string;
begin
  Result := False;
  Document := nil;
  if (Index < 0) or (Index >= FEntries.Count) then
    Exit;
  Path := FEntries[Index].FilePath;
  if FDocuments.TryGet(Path, Document) then
    Exit(Assigned(Document));
  Loader := TJsonSchemaLoader.Create;
  try
    Document := Loader.LoadDocumentFromFile(Path);
    FDocuments.Add(Path, Document);
    Result := True;
  finally
    Loader.Free;
  end;
end;

function TSchemaCatalog.Count: Integer;
begin
  Result := FEntries.Count;
end;

function TSchemaCatalog.Entry(Index: Integer): TSchemaCatalogEntry;
begin
  Result := FEntries[Index];
end;

function TSchemaCatalog.FindByName(const Name: string): Integer;
var
  I: Integer;
  Wanted: string;
begin
  Result := -1;
  Wanted := CanonicalName(Name);
  if Wanted = '' then
    Exit;
  for I := 0 to FEntries.Count - 1 do
    if SameText(CanonicalName(EntrySchemaName(FEntries[I])), Wanted) or
      SameText(CanonicalName(FEntries[I].DisplayName), Wanted) then
      Exit(I);
end;

function TSchemaCatalog.FindByPath(const Path: string): Integer;
var
  I: Integer;
begin
  Result := -1;
  for I := 0 to FEntries.Count - 1 do
    if SameText(FEntries[I].FilePath, Path) then
      Exit(I);
end;

function TSchemaCatalog.TryResolveSchema(const Name: string;
  out Node: TSchemaNode): Boolean;
var
  I: Integer;
  Wanted: string;
  Document: TSchemaDocument;
begin
  Result := False;
  Node := nil;
  I := FindByName(Name);
  if (I >= 0) and TryLoadDocument(I, Document) then
  begin
    Node := Document.Root;
    Exit(Assigned(Node));
  end;

  Wanted := CanonicalName(Name);
  if Wanted = '' then
    Exit;
  for I := 0 to FEntries.Count - 1 do
    if TryLoadDocument(I, Document) and Assigned(Document.Root) and
      SameText(CanonicalName(Document.Root.Title), Wanted) then
    begin
      Node := Document.Root;
      Exit(True);
    end;
end;

end.
