unit TypedStepSchemas;

interface

uses
  Spring.Collections,
  SchemaNode,
  SchemaDocument;

type
  TTypedStepSchemas = class
  private
    class var FSchemasRoot: string;
    class var FCache: IDictionary<string, TSchemaDocument>;
    class var FTitleToStepId: IDictionary<string, string>;
    class function StepFilename(const AStepId: string): string;
    class procedure EnsureMaps;
    class procedure IndexDocument(const AStepId: string; ADoc: TSchemaDocument);
    class procedure WarmStepIndex;
  public
    class procedure SetSchemasRoot(const APath: string);
    class function GetSchemasRoot: string;
    class function HasStepSchema(const AStepId: string): Boolean;
    class function TryGetStepIdForTitle(const ATitle: string): string;
    class function TryLoadStepRoot(const AStepId: string; out ARoot: TSchemaNode): Boolean;
    class function LoadStepRoot(const AStepId: string): TSchemaNode;
    class procedure ClearCache;
  end;

implementation

uses
  System.SysUtils,
  System.IOUtils,
  JsonSchemaLoader;

class procedure TTypedStepSchemas.EnsureMaps;
begin
  if not Assigned(FCache) then
    FCache := TCollections.CreateDictionary<string, TSchemaDocument>;
  if not Assigned(FTitleToStepId) then
    FTitleToStepId := TCollections.CreateDictionary<string, string>;
end;

class procedure TTypedStepSchemas.SetSchemasRoot(const APath: string);
begin
  if SameText(FSchemasRoot, APath) then
    Exit;
  FSchemasRoot := APath;
  ClearCache;
  WarmStepIndex;
end;

class function TTypedStepSchemas.GetSchemasRoot: string;
begin
  Result := FSchemasRoot;
end;

class procedure TTypedStepSchemas.ClearCache;
var
  Key: string;
  Doc: TSchemaDocument;
begin
  if Assigned(FCache) then
  begin
    for Key in FCache.Keys do
    begin
      Doc := FCache[Key];
      Doc.Free;
    end;
    FCache.Clear;
  end;
  if Assigned(FTitleToStepId) then
    FTitleToStepId.Clear;
end;

class procedure TTypedStepSchemas.IndexDocument(const AStepId: string;
  ADoc: TSchemaDocument);
var
  Title: string;
begin
  if not Assigned(ADoc) or not Assigned(ADoc.Root) then
    Exit;
  Title := ADoc.Root.Title;
  if Title = '' then
    Exit;
  FTitleToStepId.AddOrSetValue(Title, LowerCase(AStepId));
end;

class procedure TTypedStepSchemas.WarmStepIndex;
var
  FileName, BaseName: string;
  Root: TSchemaNode;
begin
  if FSchemasRoot = '' then
    Exit;
  EnsureMaps;
  for FileName in TDirectory.GetFiles(FSchemasRoot, '*.schema.json',
    TSearchOption.soTopDirectoryOnly) do
  begin
    BaseName := TPath.GetFileNameWithoutExtension(FileName);
    TryLoadStepRoot(BaseName, Root);
    if SameText(BaseName, 'validation_monte_carlo') then
      TryLoadStepRoot('validation', Root);
  end;
end;

class function TTypedStepSchemas.StepFilename(const AStepId: string): string;
begin
  if SameText(AStepId, 'validation') then
    Result := 'validation_monte_carlo.schema.json'
  else if SameText(AStepId, 'validator') then
    Result := 'predictor.schema.json'
  else
    Result := AStepId + '.schema.json';
end;

class function TTypedStepSchemas.HasStepSchema(const AStepId: string): Boolean;
var
  Root: TSchemaNode;
begin
  Result := TryLoadStepRoot(AStepId, Root);
end;

class function TTypedStepSchemas.TryGetStepIdForTitle(const ATitle: string): string;
begin
  Result := '';
  if (ATitle = '') or not Assigned(FTitleToStepId) then
    Exit;
  if not FTitleToStepId.TryGetValue(ATitle, Result) then
    Result := '';
end;

class function TTypedStepSchemas.TryLoadStepRoot(const AStepId: string;
  out ARoot: TSchemaNode): Boolean;
var
  Doc: TSchemaDocument;
  Loader: TJsonSchemaLoader;
  Path: string;
  CacheKey: string;
begin
  ARoot := nil;
  Result := False;
  if FSchemasRoot = '' then
    Exit;
  EnsureMaps;
  CacheKey := LowerCase(AStepId);
  if FCache.TryGetValue(CacheKey, Doc) then
  begin
    ARoot := Doc.Root;
    Exit(Assigned(ARoot));
  end;
  Path := TPath.Combine(FSchemasRoot, StepFilename(AStepId));
  if not TFile.Exists(Path) then
    Exit;
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(Path);
    FCache.Add(CacheKey, Doc);
    IndexDocument(AStepId, Doc);
    ARoot := Doc.Root;
    Result := Assigned(ARoot);
  finally
    Loader.Free;
  end;
end;

class function TTypedStepSchemas.LoadStepRoot(const AStepId: string): TSchemaNode;
begin
  if not TryLoadStepRoot(AStepId, Result) then
    raise Exception.CreateFmt('Typed step schema not found for id: %s', [AStepId]);
end;

initialization

finalization
  TTypedStepSchemas.ClearCache;
  TTypedStepSchemas.FCache := nil;
  TTypedStepSchemas.FTitleToStepId := nil;

end.
