unit SchemaCatalog;

interface

uses
  System.Generics.Collections,
  System.SysUtils;

type
  TSchemaCatalogEntry = record
    DisplayName: string;
    FilePath: string;
  end;

  TSchemaCatalog = class
  private
    FEntries: TList<TSchemaCatalogEntry>;
    procedure ScanDirectory(const Root: string; const Relative: string);
  public
    constructor Create;
    destructor Destroy; override;
    procedure LoadFromRoot(const SchemasRoot: string);
    function Count: Integer;
    function Entry(Index: Integer): TSchemaCatalogEntry;
    function FindByPath(const Path: string): Integer;
  end;

implementation

uses
  System.IOUtils;

constructor TSchemaCatalog.Create;
begin
  inherited Create;
  FEntries := TList<TSchemaCatalogEntry>.Create;
end;

destructor TSchemaCatalog.Destroy;
begin
  FEntries.Free;
  inherited Destroy;
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
  ScanDirectory(SchemasRoot, '');
  FEntries.Sort(
    TComparer<TSchemaCatalogEntry>.Construct(
      function(const Left, Right: TSchemaCatalogEntry): Integer
      begin
        Result := CompareText(Left.DisplayName, Right.DisplayName);
      end));
end;

function TSchemaCatalog.Count: Integer;
begin
  Result := FEntries.Count;
end;

function TSchemaCatalog.Entry(Index: Integer): TSchemaCatalogEntry;
begin
  Result := FEntries[Index];
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

end.
