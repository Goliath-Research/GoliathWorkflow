unit DataTypeSchemaLoaderTests;

interface

uses
  DUnitX.TestFramework,
  DataTypeSchemaLoader,
  SchemaNode,
  Spring.Collections;

type
  [TestFixture]
  TDataTypeSchemaLoaderTests = class
  private
    FTypes: IDictionary<string, TDataTypeInfo>;
    function Fetch(const AName: string; out Info: TDataTypeInfo): Boolean;
    function MakeInfo(const AName, AKind: string): TDataTypeInfo;
  public
    [Setup]
    procedure Setup;
    [Test]
    procedure PrimitiveKindsMap;
    [Test]
    procedure ObjectFieldsAndRequired;
    [Test]
    procedure NestedObjectAndArray;
    [Test]
    procedure EnumValuesOnStringNode;
    [Test]
    procedure SelfReferenceDoesNotRecurseForever;
    [Test]
    procedure FieldKeepsItsDataTypeName;
    [Test]
    procedure TypeTextDescribesFieldShape;
  end;

implementation

uses
  System.SysUtils,
  SchemaDefaults,
  SchemaTypeText,
  System.JSON;

procedure TDataTypeSchemaLoaderTests.Setup;
begin
  FTypes := TCollections.CreateDictionary<string, TDataTypeInfo>;
end;

function TDataTypeSchemaLoaderTests.MakeInfo(const AName, AKind: string): TDataTypeInfo;
begin
  Result := Default(TDataTypeInfo);
  Result.Name := AName;
  Result.Kind := AKind;
end;

function TDataTypeSchemaLoaderTests.Fetch(const AName: string;
  out Info: TDataTypeInfo): Boolean;
begin
  Result := FTypes.TryGetValue(LowerCase(AName), Info);
end;

procedure TDataTypeSchemaLoaderTests.PrimitiveKindsMap;
var
  Loader: TDataTypeSchemaLoader;
  Node: TSchemaNode;
begin
  FTypes.Add('string', MakeInfo('string', 'string'));
  FTypes.Add('int', MakeInfo('int', 'int'));
  FTypes.Add('bool', MakeInfo('bool', 'bool'));
  FTypes.Add('number', MakeInfo('number', 'number'));
  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Node := Loader.Load('int');
    Assert.AreEqual(Ord(skInteger), Ord(Node.Kind));
    Node := Loader.Load('bool');
    Assert.AreEqual(Ord(skBoolean), Ord(Node.Kind));
    Node := Loader.Load('number');
    Assert.AreEqual(Ord(skNumber), Ord(Node.Kind));
    Node := Loader.Load('string');
    Assert.AreEqual(Ord(skString), Ord(Node.Kind));
  finally
    Loader.Free;
  end;
end;

procedure TDataTypeSchemaLoaderTests.ObjectFieldsAndRequired;
var
  Loader: TDataTypeSchemaLoader;
  Obj: TDataTypeInfo;
  Node: TSchemaNode;
  Prop: TSchemaProperty;
begin
  FTypes.Add('string', MakeInfo('string', 'string'));
  FTypes.Add('int', MakeInfo('int', 'int'));
  Obj := MakeInfo('SampleIn', 'object');
  SetLength(Obj.Fields, 2);
  Obj.Fields[0].FieldName := 'sample_id';
  Obj.Fields[0].FieldTypeName := 'string';
  Obj.Fields[0].FieldTypeKind := 'string';
  Obj.Fields[0].Required := True;
  Obj.Fields[1].FieldName := 'optional_n';
  Obj.Fields[1].FieldTypeName := 'int';
  Obj.Fields[1].FieldTypeKind := 'int';
  Obj.Fields[1].Required := False;
  FTypes.Add('samplein', Obj);

  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Node := Loader.Load('SampleIn');
    Assert.AreEqual(Ord(skObject), Ord(Node.Kind));
    Assert.AreEqual(2, Node.PropertyCount);
    Prop := Node.FindProperty('sample_id');
    Assert.IsNotNull(Prop);
    Assert.IsTrue(TSchemaNode(Prop.Node).Required);
    Prop := Node.FindProperty('optional_n');
    Assert.IsFalse(TSchemaNode(Prop.Node).Required);
    Assert.AreEqual(Ord(skInteger), Ord(TSchemaNode(Prop.Node).Kind));
  finally
    Loader.Free;
  end;
end;

procedure TDataTypeSchemaLoaderTests.NestedObjectAndArray;
var
  Loader: TDataTypeSchemaLoader;
  Inner, Outer, Arr: TDataTypeInfo;
  Node: TSchemaNode;
  Items: TSchemaNode;
begin
  FTypes.Add('string', MakeInfo('string', 'string'));
  Inner := MakeInfo('Point', 'object');
  SetLength(Inner.Fields, 1);
  Inner.Fields[0].FieldName := 'x';
  Inner.Fields[0].FieldTypeName := 'string';
  Inner.Fields[0].FieldTypeKind := 'string';
  Inner.Fields[0].Required := True;
  FTypes.Add('point', Inner);

  Arr := MakeInfo('PointList', 'array');
  Arr.ElementTypeName := 'Point';
  FTypes.Add('pointlist', Arr);

  Outer := MakeInfo('Box', 'object');
  SetLength(Outer.Fields, 1);
  Outer.Fields[0].FieldName := 'points';
  Outer.Fields[0].FieldTypeName := 'PointList';
  Outer.Fields[0].FieldTypeKind := 'array';
  Outer.Fields[0].Required := True;
  FTypes.Add('box', Outer);

  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Node := Loader.Load('Box');
    Assert.AreEqual(Ord(skArray), Ord(TSchemaNode(Node.FindProperty('points').Node).Kind));
    Items := TSchemaNode(Node.FindProperty('points').Node).ItemsSchema;
    Assert.IsNotNull(Items);
    Assert.AreEqual(Ord(skObject), Ord(Items.Kind));
    Assert.IsNotNull(Items.FindProperty('x'));
  finally
    Loader.Free;
  end;
end;

procedure TDataTypeSchemaLoaderTests.EnumValuesOnStringNode;
var
  Loader: TDataTypeSchemaLoader;
  Info: TDataTypeInfo;
  Node: TSchemaNode;
begin
  Info := MakeInfo('Mode', 'enum');
  SetLength(Info.EnumValues, 2);
  Info.EnumValues[0] := 'fast';
  Info.EnumValues[1] := 'accurate';
  FTypes.Add('mode', Info);

  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Node := Loader.Load('Mode');
    Assert.AreEqual(Ord(skString), Ord(Node.Kind));
    Assert.AreEqual(2, Node.EnumValues.Count);
    Assert.AreEqual('fast', Node.EnumValues[0]);
  finally
    Loader.Free;
  end;
end;

procedure TDataTypeSchemaLoaderTests.FieldKeepsItsDataTypeName;
var
  Loader: TDataTypeSchemaLoader;
  Obj, Inner: TDataTypeInfo;
  Field: TSchemaNode;
begin
  Inner := MakeInfo('RemediationTrigger', 'object');
  FTypes.Add('remediationtrigger', Inner);
  Obj := MakeInfo('QcIn', 'object');
  SetLength(Obj.Fields, 1);
  Obj.Fields[0].FieldName := 'remediationTrigger';
  Obj.Fields[0].FieldTypeName := 'RemediationTrigger';
  Obj.Fields[0].FieldTypeKind := 'object';
  FTypes.Add('qcin', Obj);

  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Field := TSchemaNode(Loader.Load('QcIn').FindProperty('remediationTrigger').Node);
    // Title carries the field name for the grid caption; TypeName must survive.
    Assert.AreEqual('remediationTrigger', Field.Title);
    Assert.AreEqual('RemediationTrigger', Field.TypeName);
  finally
    Loader.Free;
  end;
end;

procedure TDataTypeSchemaLoaderTests.TypeTextDescribesFieldShape;
var
  Loader: TDataTypeSchemaLoader;
  Obj, Arr, Mode: TDataTypeInfo;
  Node: TSchemaNode;
  Field: TSchemaNode;
begin
  FTypes.Add('string', MakeInfo('string', 'string'));
  Arr := MakeInfo('project.input.paths.array', 'array');
  Arr.ElementTypeName := 'string';
  FTypes.Add('project.input.paths.array', Arr);
  Mode := MakeInfo('Mode', 'enum');
  SetLength(Mode.EnumValues, 2);
  Mode.EnumValues[0] := 'fast';
  Mode.EnumValues[1] := 'accurate';
  FTypes.Add('mode', Mode);

  Obj := MakeInfo('project.input', 'object');
  SetLength(Obj.Fields, 3);
  Obj.Fields[0].FieldName := 'projectPath';
  Obj.Fields[0].FieldTypeName := 'string';
  Obj.Fields[0].FieldTypeKind := 'string';
  Obj.Fields[1].FieldName := 'paths';
  Obj.Fields[1].FieldTypeName := 'project.input.paths.array';
  Obj.Fields[1].FieldTypeKind := 'array';
  Obj.Fields[2].FieldName := 'mode';
  Obj.Fields[2].FieldTypeName := 'Mode';
  Obj.Fields[2].FieldTypeKind := 'enum';
  FTypes.Add('project.input', Obj);

  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Node := Loader.Load('project.input');
    Assert.AreEqual('string',
      TSchemaTypeText.Describe(TSchemaNode(Node.FindProperty('projectPath').Node)));
    Assert.AreEqual('array<string>',
      TSchemaTypeText.Describe(TSchemaNode(Node.FindProperty('paths').Node)));
    Assert.AreEqual('Mode enum(fast | accurate)',
      TSchemaTypeText.Describe(TSchemaNode(Node.FindProperty('mode').Node)));

    // wf.data_type carries no defaults today, so the suffix only shows up once
    // a node actually has one.
    Field := TSchemaNode(Node.FindProperty('projectPath').Node);
    Assert.AreEqual('string', TSchemaTypeText.DescribeWithDefault(Field));
    Field.DefaultValue := TJSONString.Create('/work/projects/demo');
    Assert.AreEqual('string = /work/projects/demo',
      TSchemaTypeText.DescribeWithDefault(Field));
  finally
    Loader.Free;
  end;
end;

procedure TDataTypeSchemaLoaderTests.SelfReferenceDoesNotRecurseForever;
var
  Loader: TDataTypeSchemaLoader;
  Info: TDataTypeInfo;
  Node: TSchemaNode;
  Preview: TJSONValue;
begin
  Info := MakeInfo('Tree', 'object');
  SetLength(Info.Fields, 1);
  Info.Fields[0].FieldName := 'child';
  Info.Fields[0].FieldTypeName := 'Tree';
  Info.Fields[0].FieldTypeKind := 'object';
  Info.Fields[0].Required := False;
  FTypes.Add('tree', Info);

  Loader := TDataTypeSchemaLoader.Create(Fetch);
  try
    Node := Loader.Load('Tree');
    Assert.AreEqual(1, Node.PropertyCount);
    Assert.AreSame(Node, TSchemaNode(Node.FindProperty('child').Node));
    Preview := TSchemaDefaults.CreatePreviewValue(Node);
    try
      Assert.IsTrue(Preview is TJSONObject);
      Assert.IsTrue(TJSONObject(Preview).GetValue('child') is TJSONObject);
    finally
      Preview.Free;
    end;
  finally
    Loader.Free;
  end;
end;

end.
