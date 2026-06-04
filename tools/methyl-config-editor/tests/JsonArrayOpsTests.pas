unit JsonArrayOpsTests;

interface

uses
  DUnitX.TestFramework;

type
  [TestFixture]
  TJsonArrayOpsTests = class
  public
    [Test]
    procedure ReplaceRemoveMove;
  end;

implementation

uses
  System.JSON,
  JsonArrayOps;

procedure TJsonArrayOpsTests.ReplaceRemoveMove;
var
  Arr: TJSONArray;
begin
  Arr := TJSONArray.Create;
  try
    Arr.AddElement(TJSONString.Create('a'));
    Arr.AddElement(TJSONString.Create('b'));
    Arr.AddElement(TJSONString.Create('c'));

    TJsonArrayOps.ReplaceElement(Arr, 1, TJSONString.Create('B'));
    Assert.AreEqual('B', Arr.Items[1].Value);

    TJsonArrayOps.MoveElement(Arr, 2, 0);
    Assert.AreEqual('c', Arr.Items[0].Value);
    Assert.AreEqual('a', Arr.Items[1].Value);
    Assert.AreEqual('B', Arr.Items[2].Value);

    TJsonArrayOps.RemoveElement(Arr, 1);
    Assert.AreEqual(2, Arr.Count);
    Assert.AreEqual('c', Arr.Items[0].Value);
    Assert.AreEqual('B', Arr.Items[1].Value);

    TJsonArrayOps.Clear(Arr);
    Assert.AreEqual(0, Arr.Count);
  finally
    Arr.Free;
  end;
end;

initialization
  TDUnitX.RegisterTestFixture(TJsonArrayOpsTests);

end.
