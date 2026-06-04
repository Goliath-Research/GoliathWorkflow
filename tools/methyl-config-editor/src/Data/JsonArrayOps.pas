unit JsonArrayOps;

interface

uses
  Spring.Collections,
  System.JSON,
  System.SysUtils;

type
  TJsonArrayOps = class
  public
    class procedure Clear(AArray: TJSONArray);
    class procedure ReplaceElement(AArray: TJSONArray; Index: Integer; AValue: TJSONValue);
    class procedure RemoveElement(AArray: TJSONArray; Index: Integer);
    class procedure MoveElement(AArray: TJSONArray; FromIndex, ToIndex: Integer);
    class procedure SetElement(AArray: TJSONArray; Index: Integer; Value: TJSONValue);
  end;

implementation

class procedure TJsonArrayOps.Clear(AArray: TJSONArray);
var
  Removed: TJSONValue;
begin
  while AArray.Count > 0 do
  begin
    Removed := AArray.Remove(0);
    Removed.Free;
  end;
end;

class procedure TJsonArrayOps.ReplaceElement(AArray: TJSONArray; Index: Integer;
  AValue: TJSONValue);
var
  I: Integer;
  Tail: IList<TJSONValue>;
  Removed: TJSONValue;
begin
  if Index < 0 then
    raise Exception.Create('Negative array index');
  Tail := TCollections.CreateObjectList<TJSONValue>(False);
  try
    for I := Index + 1 to AArray.Count - 1 do
      Tail.Add(AArray.Items[I].Clone as TJSONValue);
    while AArray.Count > Index do
    begin
      Removed := AArray.Remove(AArray.Count - 1);
      Removed.Free;
    end;
    AArray.AddElement(AValue);
    for I := 0 to Tail.Count - 1 do
      AArray.AddElement(Tail[I]);
  finally
    Tail := nil;
  end;
end;

class procedure TJsonArrayOps.RemoveElement(AArray: TJSONArray; Index: Integer);
var
  I: Integer;
  Values: IList<TJSONValue>;
begin
  Values := TCollections.CreateObjectList<TJSONValue>(False);
  try
    for I := 0 to AArray.Count - 1 do
      if I <> Index then
        Values.Add(AArray.Items[I].Clone as TJSONValue);
    Clear(AArray);
    for I := 0 to Values.Count - 1 do
      AArray.AddElement(Values[I]);
  finally
    Values := nil;
  end;
end;

class procedure TJsonArrayOps.MoveElement(AArray: TJSONArray; FromIndex,
  ToIndex: Integer);
var
  I: Integer;
  Values: IList<TJSONValue>;
  Moving: TJSONValue;
begin
  Values := TCollections.CreateObjectList<TJSONValue>(False);
  try
    for I := 0 to AArray.Count - 1 do
      Values.Add(AArray.Items[I].Clone as TJSONValue);
    Moving := Values[FromIndex];
    Values.Delete(FromIndex);
    Values.Insert(ToIndex, Moving);
    Clear(AArray);
    for I := 0 to Values.Count - 1 do
      AArray.AddElement(Values[I]);
  finally
    Values := nil;
  end;
end;

class procedure TJsonArrayOps.SetElement(AArray: TJSONArray; Index: Integer;
  Value: TJSONValue);
begin
  ReplaceElement(AArray, Index, Value);
end;

end.
