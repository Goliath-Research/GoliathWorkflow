unit SchemaLoaderTests;

interface

uses
  DUnitX.TestFramework;

type
  [TestFixture]
  TSchemaLoaderTests = class
  private
    function RepoRoot: string;
    function SchemaPath(const Relative: string): string;
  public
    [Test]
    procedure LoadProjectConfigSchema;
    [Test]
    procedure NullableAnyOfNormalized;
    [Test]
    procedure RefDefsResolveGroupConfig;
    [Test]
    procedure MonteCarloDiscriminatorOneOf;
    [Test]
    procedure CentroidSchemaLoads;
  end;

implementation

uses
  System.IOUtils,
  System.SysUtils,
  JsonSchemaLoader,
  SchemaNode,
  SchemaDocument;

function TSchemaLoaderTests.RepoRoot: string;
var
  Dir: string;
  Candidate: string;
begin
  Dir := TPath.GetFullPath(ExtractFilePath(ParamStr(0)));
  while Dir <> '' do
  begin
    Candidate := TPath.Combine(Dir, 'schemas\config');
    if TDirectory.Exists(Candidate) then
      Exit(Dir);
    Dir := TPath.GetDirectoryName(ExcludeTrailingPathDelimiter(Dir));
  end;
  raise Exception.Create('Could not locate repo schemas/config directory from test runner path');
end;

function TSchemaLoaderTests.SchemaPath(const Relative: string): string;
begin
  Result := TPath.Combine(TPath.Combine(RepoRoot, 'schemas\config'), Relative);
end;

procedure TSchemaLoaderTests.LoadProjectConfigSchema;
var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(SchemaPath('project_config.schema.json'));
    try
      Assert.IsNotNull(Doc.Root);
      Assert.AreEqual(TSchemaKind.skObject, Doc.Root.Kind);
      Assert.IsTrue(Doc.Root.FindProperty('project_name') <> nil);
      Assert.IsTrue(Doc.Root.FindProperty('output_base') <> nil);
    finally
      Doc.Free;
    end;
  finally
    Loader.Free;
  end;
end;

procedure TSchemaLoaderTests.NullableAnyOfNormalized;
var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
  Prop: TSchemaProperty;
  Node: TSchemaNode;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(SchemaPath('project_config.schema.json'));
    try
      Prop := Doc.Root.FindProperty('samples_base_path');
      Assert.IsNotNull(Prop);
      Node := TSchemaNode(Prop.Node);
      Assert.IsTrue(Node.Nullable);
      Assert.AreEqual(TSchemaKind.skString, Node.Kind);
    finally
      Doc.Free;
    end;
  finally
    Loader.Free;
  end;
end;

procedure TSchemaLoaderTests.RefDefsResolveGroupConfig;
var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
  Prop: TSchemaProperty;
  GroupsNode: TSchemaNode;
  Items: TSchemaNode;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(SchemaPath('project_config.schema.json'));
    try
      Prop := Doc.Root.FindProperty('control');
      Assert.IsNotNull(Prop);
      Prop := TSchemaNode(Prop.Node).FindProperty('groups');
      Assert.IsNotNull(Prop);
      GroupsNode := TSchemaNode(Prop.Node);
      Assert.AreEqual(TSchemaKind.skArray, GroupsNode.Kind);
      Items := GroupsNode.ItemsSchema;
      Assert.IsNotNull(Items);
      Assert.AreEqual(TSchemaKind.skObject, Items.Kind);
      Assert.IsTrue(Items.FindProperty('label') <> nil);
      Assert.IsTrue(Items.FindProperty('stages') <> nil);
    finally
      Doc.Free;
    end;
  finally
    Loader.Free;
  end;
end;

procedure TSchemaLoaderTests.MonteCarloDiscriminatorOneOf;

  function HasOneOf(const Node: TSchemaNode): Boolean;
  var
    I: Integer;
  begin
    Result := False;
    if not Assigned(Node) then
      Exit;
    if Node.OneOfBranches.Count > 0 then
      Exit(True);
    for I := 0 to Node.PropertyCount - 1 do
      if HasOneOf(TSchemaNode(Node.Properties[I].Node)) then
        Exit(True);
    if Assigned(Node.ItemsSchema) and HasOneOf(Node.ItemsSchema) then
      Exit(True);
  end;

var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(SchemaPath('validation_monte_carlo.schema.json'));
    try
      Assert.IsTrue(HasOneOf(Doc.Root), 'Expected nested oneOf/discriminator in Monte Carlo schema');
    finally
      Doc.Free;
    end;
  finally
    Loader.Free;
  end;
end;

procedure TSchemaLoaderTests.CentroidSchemaLoads;
var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(SchemaPath('centroid.schema.json'));
    try
      Assert.IsNotNull(Doc.Root);
      Assert.AreEqual(TSchemaKind.skObject, Doc.Root.Kind);
    finally
      Doc.Free;
    end;
  finally
    Loader.Free;
  end;
end;

initialization
  TDUnitX.RegisterTestFixture(TSchemaLoaderTests);

end.
