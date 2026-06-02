unit SchemaValidator;

interface

uses
  System.JSON,
  System.SysUtils,
  SchemaNode;

type
  TSchemaValidator = class
  public
    class function ValidateValue(ANode: TSchemaNode; AValue: TJSONValue;
      out ErrorMessage: string): Boolean;
    class function ValidateObject(ANode: TSchemaNode; AObject: TJSONObject;
      out ErrorMessage: string): Boolean;
  end;

implementation

uses
  SchemaBranchResolver,
  SchemaValueSummary;

class function TSchemaValidator.ValidateValue(ANode: TSchemaNode;
  AValue: TJSONValue; out ErrorMessage: string): Boolean;
var
  S: string;
  N: Double;
  I: Integer;
begin
  Result := True;
  ErrorMessage := '';
  if not Assigned(ANode) then
    Exit;
  if TSchemaValueSummary.IsNullValue(AValue) then
  begin
    if ANode.Required and not ANode.Nullable then
    begin
      ErrorMessage := 'Value is required';
      Exit(False);
    end;
    Exit(True);
  end;
  case ANode.Kind of
    skBoolean:
      if not ((AValue is TJSONTrue) or (AValue is TJSONFalse)) then
      begin
        ErrorMessage := 'Expected boolean';
        Exit(False);
      end;
    skInteger:
      if not (AValue is TJSONNumber) then
      begin
        ErrorMessage := 'Expected integer';
        Exit(False);
      end
      else
      begin
        N := TJSONNumber(AValue).AsDouble;
        if Frac(N) <> 0 then
        begin
          ErrorMessage := 'Expected integer value';
          Exit(False);
        end;
        if ANode.HasMinimum and (N < ANode.Minimum) then
        begin
          ErrorMessage := Format('Minimum is %g', [ANode.Minimum]);
          Exit(False);
        end;
        if ANode.HasMaximum and (N > ANode.Maximum) then
        begin
          ErrorMessage := Format('Maximum is %g', [ANode.Maximum]);
          Exit(False);
        end;
      end;
    skNumber:
      if not (AValue is TJSONNumber) then
      begin
        ErrorMessage := 'Expected number';
        Exit(False);
      end
      else
      begin
        N := TJSONNumber(AValue).AsDouble;
        if ANode.HasMinimum and (N < ANode.Minimum) then
        begin
          ErrorMessage := Format('Minimum is %g', [ANode.Minimum]);
          Exit(False);
        end;
        if ANode.HasMaximum and (N > ANode.Maximum) then
        begin
          ErrorMessage := Format('Maximum is %g', [ANode.Maximum]);
          Exit(False);
        end;
      end;
    skString:
      if not (AValue is TJSONString) then
      begin
        ErrorMessage := 'Expected string';
        Exit(False);
      end
      else
      begin
        S := TJSONString(AValue).Value;
        if (ANode.MinLength >= 0) and (Length(S) < ANode.MinLength) then
        begin
          ErrorMessage := Format('Minimum length is %d', [ANode.MinLength]);
          Exit(False);
        end;
        if Length(ANode.EnumValues) > 0 then
        begin
          for I := 0 to High(ANode.EnumValues) do
            if ANode.EnumValues[I] = S then
              Exit(True);
          ErrorMessage := 'Value must be one of the allowed enum values';
          Exit(False);
        end;
      end;
    skObject, skDictionary:
      if not (AValue is TJSONObject) then
      begin
        ErrorMessage := 'Expected object';
        Exit(False);
      end
      else
        Exit(ValidateObject(ANode, TJSONObject(AValue), ErrorMessage));
    skArray:
      if not (AValue is TJSONArray) then
      begin
        ErrorMessage := 'Expected array';
        Exit(False);
      end;
  end;
end;

class function TSchemaValidator.ValidateObject(ANode: TSchemaNode;
  AObject: TJSONObject; out ErrorMessage: string): Boolean;
var
  Effective: TSchemaNode;
  I: Integer;
  Prop: TSchemaProperty;
  PropNode: TSchemaNode;
  Val: TJSONValue;
  Pair: TJSONPair;
begin
  Result := True;
  ErrorMessage := '';
  Effective := TSchemaBranchResolver.ResolveObjectSchema(ANode, AObject);
  for I := 0 to Effective.PropertyCount - 1 do
  begin
    Prop := Effective.Properties[I];
    PropNode := TSchemaNode(Prop.Node);
    Val := AObject.GetValue(Prop.Name);
    if PropNode.Required and TSchemaValueSummary.IsNullValue(Val) then
    begin
      ErrorMessage := Format('Required property missing: %s', [Prop.Name]);
      Exit(False);
    end;
    if Assigned(Val) then
      if not ValidateValue(PropNode, Val, ErrorMessage) then
      begin
        ErrorMessage := Format('%s: %s', [Prop.Name, ErrorMessage]);
        Exit(False);
      end;
  end;
  if Effective.AdditionalPropertiesAllowed then
    Exit(True);
  for Pair in AObject do
  begin
    if Effective.FindProperty(Pair.JsonString.Value) = nil then
    begin
      ErrorMessage := Format('Additional property not allowed: %s', [Pair.JsonString.Value]);
      Exit(False);
    end;
  end;
end;

end.
