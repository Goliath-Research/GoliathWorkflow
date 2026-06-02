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
    class function StepFilename(const AStepId: string): string;
  public
    class procedure SetSchemasRoot(const APath: string);
    class function GetSchemasRoot: string;
    class function TryLoadStepRoot(const AStepId: string; out ARoot: TSchemaNode): Boolean;
    class function LoadStepRoot(const AStepId: string): TSchemaNode;
    class procedure ClearCache;
  end;

implementation

uses
  System.SysUtils,
  System.IOUtils,
  JsonSchemaLoader;

class procedure TTypedStepSchemas.SetSchemasRoot(const APath: string);
begin
  if SameText(FSchemasRoot, APath) then
    Exit;
  FSchemasRoot := APath;
  ClearCache;
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
  if not Assigned(FCache) then
    Exit;
  for Key in FCache.Keys do
  begin
    Doc := FCache[Key];
    Doc.Free;
  end;
  FCache.Clear;
end;

class function TTypedStepSchemas.StepFilename(const AStepId: string): string;
begin
  if SameText(AStepId, 'detection') then
    Result := 'detection.schema.json'
  else
    Result := AStepId + '.schema.json';
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
  if not Assigned(FCache) then
    FCache := TCollections.CreateDictionary<string, TSchemaDocument>;
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

end.
