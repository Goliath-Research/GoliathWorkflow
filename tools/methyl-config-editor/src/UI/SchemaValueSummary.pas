unit SchemaValueSummary;

interface

uses
  System.JSON,
  System.SysUtils,
  SchemaNode;

type
  TSchemaValueSummary = class
  public
    class function Describe(ANode: TSchemaNode; AValue: TJSONValue): string;
    class function IsNullValue(AValue: TJSONValue): Boolean;
  end;

implementation

class function TSchemaValueSummary.IsNullValue(AValue: TJSONValue): Boolean;
begin
  Result := not Assigned(AValue) or (AValue is TJSONNull);
end;

class function TSchemaValueSummary.Describe(ANode: TSchemaNode;
  AValue: TJSONValue): string;
begin
  if IsNullValue(AValue) then
    Exit('(null)');
  if not Assigned(ANode) then
    Exit(AValue.Value);
  case ANode.Kind of
    skBoolean:
      if AValue is TJSONTrue then
        Exit('True')
      else if AValue is TJSONFalse then
        Exit('False');
    skInteger, skNumber:
      Exit(AValue.Value);
    skString:
      if AValue is TJSONString then
      begin
        if Length(TJSONString(AValue).Value) > 48 then
          Result := Copy(TJSONString(AValue).Value, 1, 45) + '...'
        else
          Result := TJSONString(AValue).Value;
        Exit;
      end;
    skObject:
      if AValue is TJSONObject then
        Exit(Format('(%d properties)', [TJSONObject(AValue).Count]));
    skArray:
      if AValue is TJSONArray then
        Exit(Format('[%d items]', [TJSONArray(AValue).Count]));
    skDictionary:
      if AValue is TJSONObject then
        Exit(Format('{%d keys}', [TJSONObject(AValue).Count]));
  end;
  Result := AValue.Value;
end;

end.
