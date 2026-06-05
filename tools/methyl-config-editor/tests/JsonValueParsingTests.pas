unit JsonValueParsingTests;

interface

uses
  DUnitX.TestFramework,
  System.JSON,
  SchemaNode;

type
  [TestFixture]
  TJsonValueParsingTests = class
  public
    [Test]
    procedure ParseBooleanValues;
    [Test]
    procedure ParseIntegerAndNumber;
    [Test]
    procedure ParseNullableString;
    [Test]
    procedure ValueToGridString_ComplexPrefix;
  end;

implementation

uses
  JsonValueParsing,
  SchemaValueSummary;

procedure TJsonValueParsingTests.ParseBooleanValues;
var
  Node: TSchemaNode;
  Parsed: TJSONValue;
  Err: string;
begin
  Node := TSchemaNode.Create;
  try
    Node.Kind := skBoolean;
    Assert.IsTrue(TJsonValueParsing.ParseGridString(Node, 'True', Parsed, Err), Err);
    try
      Assert.IsTrue(Parsed is TJSONTrue);
    finally
      Parsed.Free;
    end;
    Assert.IsTrue(TJsonValueParsing.ParseGridString(Node, 'False', Parsed, Err), Err);
    try
      Assert.IsTrue(Parsed is TJSONFalse);
    finally
      Parsed.Free;
    end;
  finally
    Node.Free;
  end;
end;

procedure TJsonValueParsingTests.ParseIntegerAndNumber;
var
  Node: TSchemaNode;
  Parsed: TJSONValue;
  Err: string;
begin
  Node := TSchemaNode.Create;
  try
    Node.Kind := skInteger;
    Assert.IsTrue(TJsonValueParsing.ParseGridString(Node, '42', Parsed, Err), Err);
    try
      Assert.AreEqual(42.0, TJSONNumber(Parsed).AsDouble);
    finally
      Parsed.Free;
    end;
    Node.Kind := skNumber;
    Assert.IsTrue(TJsonValueParsing.ParseGridString(Node, '3.14', Parsed, Err), Err);
    try
      Assert.AreEqual(3.14, TJSONNumber(Parsed).AsDouble, 0.001);
    finally
      Parsed.Free;
    end;
  finally
    Node.Free;
  end;
end;

procedure TJsonValueParsingTests.ParseNullableString;
var
  Node: TSchemaNode;
  Parsed: TJSONValue;
  Err: string;
begin
  Node := TSchemaNode.Create;
  try
    Node.Kind := skString;
    Node.Nullable := True;
    Assert.IsTrue(TJsonValueParsing.ParseGridString(Node, '(null)', Parsed, Err), Err);
    try
      Assert.IsTrue(TSchemaValueSummary.IsNullValue(Parsed));
    finally
      Parsed.Free;
    end;
    Assert.IsTrue(TJsonValueParsing.ParseGridString(Node, 'hello', Parsed, Err), Err);
    try
      Assert.AreEqual('hello', TJSONString(Parsed).Value);
    finally
      Parsed.Free;
    end;
  finally
    Node.Free;
  end;
end;

procedure TJsonValueParsingTests.ValueToGridString_ComplexPrefix;
var
  Node: TSchemaNode;
  Obj: TJSONObject;
  S: string;
begin
  Node := TSchemaNode.Create;
  Obj := TJSONObject.Create;
  try
    Node.Kind := skObject;
    Obj.AddPair('a', TJSONNumber.Create(1));
    S := TJsonValueParsing.ValueToGridString(Node, Obj);
    Assert.IsTrue(S.StartsWith(TJsonValueParsing.ComplexGridPrefix));
  finally
    Obj.Free;
    Node.Free;
  end;
end;

initialization
  TDUnitX.RegisterTestFixture(TJsonValueParsingTests);

end.
