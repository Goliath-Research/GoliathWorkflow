unit JsonPathTests;

interface

uses
  DUnitX.TestFramework;

type
  [TestFixture]
  TJsonPathTests = class
  public
    [Test]
    procedure GetSetNestedObject;
    [Test]
    procedure EnsureArrayCreatesPath;
    [Test]
    procedure CloneValueDeepCopy;
  end;

implementation

uses
  System.JSON,
  JsonPath;

procedure TJsonPathTests.GetSetNestedObject;
var
  Root: TJSONObject;
  Val: TJSONValue;
begin
  Root := TJSONObject.Create;
  try
    Root.AddPair('a', TJSONObject.Create);
    TJSONObject(Root.GetValue('a')).AddPair('b', TJSONString.Create('hello'));
    Val := TJsonPath.GetValue(Root, 'a/b');
    Assert.IsNotNull(Val);
    Assert.AreEqual('hello', Val.Value);
    TJsonPath.SetValue(Root, 'a/b', TJSONString.Create('world'));
    Val := TJsonPath.GetValue(Root, 'a/b');
    Assert.AreEqual('world', Val.Value);
  finally
    Root.Free;
  end;
end;

procedure TJsonPathTests.EnsureArrayCreatesPath;
var
  Root: TJSONObject;
  Arr: TJSONArray;
begin
  Root := TJSONObject.Create;
  try
    Arr := TJsonPath.EnsureArray(Root, 'items');
    Assert.IsNotNull(Arr);
    Assert.AreEqual(0, Arr.Count);
    Arr.AddElement(TJSONString.Create('x'));
    Assert.AreEqual(1, TJsonPath.GetArray(Root, 'items').Count);
  finally
    Root.Free;
  end;
end;

procedure TJsonPathTests.CloneValueDeepCopy;
var
  Root, Clone: TJSONObject;
begin
  Root := TJSONObject.Create;
  try
    Root.AddPair('n', TJSONNumber.Create(42));
    Clone := TJsonPath.CloneValue(Root) as TJSONObject;
    try
      Assert.AreEqual('42', Clone.GetValue('n').Value);
      TJSONObject(Clone.GetValue('n')).AsInt := 99;
      Assert.AreEqual('42', Root.GetValue('n').Value);
    finally
      Clone.Free;
    end;
  finally
    Root.Free;
  end;
end;

initialization
  TDUnitX.RegisterTestFixture(TJsonPathTests);

end.
