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
    function FixturePath(const Relative: string): string;
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
    [Test]
    procedure ExternalFileRefResolves;
    [Test]
    procedure NestedCrossDirectoryRefResolves;
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

function TSchemaLoaderTests.FixturePath(const Relative: string): string;
var
  Dir: string;
  Candidate: string;
begin
  Dir := TPath.GetFullPath(ExtractFilePath(ParamStr(0)));
  while Dir <> '' do
  begin
    Candidate := TPath.Combine(Dir, 'tests\fixtures');
    if TDirectory.Exists(Candidate) then
      Exit(TPath.Combine(Candidate, Relative));
    Candidate := TPath.Combine(Dir, 'tools\methyl-config-editor\tests\fixtures');
    if TDirectory.Exists(Candidate) then
      Exit(TPath.Combine(Candidate, Relative));
    Dir := TPath.GetDirectoryName(ExcludeTrailingPathDelimiter(Dir));
  end;
  raise Exception.Create('Could not locate tests/fixtures directory from test runner path');
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

procedure TSchemaLoaderTests.ExternalFileRefResolves;
var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
  Prop: TSchemaProperty;
  WidgetNode: TSchemaNode;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(FixturePath('container.schema.json'));
    try
      Prop := Doc.Root.FindProperty('widget');
      Assert.IsNotNull(Prop);
      WidgetNode := TSchemaNode(Prop.Node);
      Assert.AreEqual(TSchemaKind.skObject, WidgetNode.Kind);
      Assert.AreEqual('Widget', WidgetNode.Title);
      Assert.IsTrue(WidgetNode.FindProperty('name') <> nil);
    finally
      Doc.Free;
    end;
  finally
    Loader.Free;
  end;
end;

procedure TSchemaLoaderTests.NestedCrossDirectoryRefResolves;
var
  Loader: TJsonSchemaLoader;
  Doc: TSchemaDocument;
  WidgetProp, PartProp: TSchemaProperty;
  WidgetNode, PartNode: TSchemaNode;
begin
  Loader := TJsonSchemaLoader.Create;
  try
    Doc := Loader.LoadDocumentFromFile(FixturePath('sub_container.schema.json'));
    try
      WidgetProp := Doc.Root.FindProperty('widget');
      Assert.IsNotNull(WidgetProp);
      WidgetNode := TSchemaNode(WidgetProp.Node);
      Assert.AreEqual('SubWidget', WidgetNode.Title);

      PartProp := WidgetNode.FindProperty('part');
      Assert.IsNotNull(PartProp);
      PartNode := TSchemaNode(PartProp.Node);
      Assert.AreEqual('Part', PartNode.Title);
      Assert.IsTrue(PartNode.FindProperty('code') <> nil);
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
