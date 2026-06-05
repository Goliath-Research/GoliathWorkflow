unit JsonValueParsing;

interface

uses
  System.JSON,
  System.SysUtils,
  SchemaNode,
  SchemaValueSummary;

type
  TJsonValueParsing = class
  public
    class function TryParseJsonFloat(const Text: string; out Value: Double): Boolean;
    class function ValueToGridString(ANode: TSchemaNode; AValue: TJSONValue): string;
    class function ParseGridString(ANode: TSchemaNode; const Text: string;
      out AValue: TJSONValue; out ErrorMessage: string): Boolean;
    class function IsComplexKind(ANode: TSchemaNode): Boolean;
    class function ComplexGridPrefix: string;
    class function IsComplexGridValue(const PropValue: string): Boolean;
  end;

implementation

class function TJsonValueParsing.TryParseJsonFloat(const Text: string;
  out Value: Double): Boolean;
var
  FormatSettings: TFormatSettings;
begin
  Result := TryStrToFloat(Text, Value);
  if Result then
    Exit;
  FormatSettings := TFormatSettings.Create('en-US');
  Result := TryStrToFloat(Text, Value, FormatSettings);
end;

class function TJsonValueParsing.ComplexGridPrefix: string;
begin
  Result := '>> ';
end;

class function TJsonValueParsing.IsComplexKind(ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode) and ANode.IsComplex;
end;

class function TJsonValueParsing.IsComplexGridValue(const PropValue: string): Boolean;
begin
  Result := PropValue.StartsWith(ComplexGridPrefix);
end;

class function TJsonValueParsing.ValueToGridString(ANode: TSchemaNode;
  AValue: TJSONValue): string;
var
  S: string;
begin
  if not Assigned(ANode) then
    Exit('');
  if IsComplexKind(ANode) then
    Exit(ComplexGridPrefix + TSchemaValueSummary.Describe(ANode, AValue));
  if TSchemaValueSummary.IsNullValue(AValue) then
    Exit('(null)');
  case ANode.Kind of
    skBoolean:
      if AValue is TJSONTrue then
        Exit('True')
      else
        Exit('False');
    skInteger, skNumber:
      Exit(AValue.Value);
    skString:
      if AValue is TJSONString then
        Exit(TJSONString(AValue).Value)
      else
        Exit(AValue.Value);
  else
    Exit(AValue.Value);
  end;
end;

class function TJsonValueParsing.ParseGridString(ANode: TSchemaNode;
  const Text: string; out AValue: TJSONValue; out ErrorMessage: string): Boolean;
var
  FloatValue: Double;
  IntValue: Int64;
  Trimmed: string;
  EnumValue: string;
begin
  Result := False;
  AValue := nil;
  ErrorMessage := '';
  if not Assigned(ANode) then
  begin
    ErrorMessage := 'Missing schema node';
    Exit;
  end;

  Trimmed := Trim(Text);
  if SameText(Trimmed, '(null)') or (Trimmed = '') then
  begin
    if ANode.Nullable or (Trimmed = '') then
    begin
      AValue := TJSONNull.Create;
      Exit(True);
    end;
    ErrorMessage := 'Value is required';
    Exit;
  end;

  case ANode.Kind of
    skBoolean:
      begin
        if SameText(Trimmed, 'True') or SameText(Trimmed, 'Yes') or (Trimmed = '1') then
          AValue := TJSONTrue.Create
        else if SameText(Trimmed, 'False') or SameText(Trimmed, 'No') or (Trimmed = '0') then
          AValue := TJSONFalse.Create
        else
        begin
          ErrorMessage := 'Expected True or False';
          Exit;
        end;
        Result := True;
      end;
    skInteger:
      begin
        if TryStrToInt64(Trimmed, IntValue) then
          AValue := TJSONNumber.Create(IntValue)
        else if TryParseJsonFloat(Trimmed, FloatValue) then
          AValue := TJSONNumber.Create(Trunc(FloatValue))
        else
        begin
          ErrorMessage := 'Expected integer';
          Exit;
        end;
        Result := True;
      end;
    skNumber:
      begin
        if TryParseJsonFloat(Trimmed, FloatValue) then
          AValue := TJSONNumber.Create(FloatValue)
        else
        begin
          ErrorMessage := 'Expected number';
          Exit;
        end;
        Result := True;
      end;
    skString:
      begin
        if ANode.EnumValues.Count > 0 then
        begin
          for EnumValue in ANode.EnumValues do
            if SameText(EnumValue, Trimmed) then
            begin
              AValue := TJSONString.Create(EnumValue);
              Exit(True);
            end;
          ErrorMessage := 'Value is not in the allowed enum list';
          Exit;
        end;
        AValue := TJSONString.Create(Trimmed);
        Result := True;
      end;
  else
    ErrorMessage := 'Unsupported scalar type';
  end;
end;

end.
