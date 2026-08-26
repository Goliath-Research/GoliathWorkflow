unit SchemaTypeText;

// ====
// Renders the *shape* of a TSchemaNode as text, for viewers that label each row
// "field : type = default" (EpiPortal pipeline profiles) so the value column
// stays free for the values the profile actually sets.
// Non-goal: validation or value formatting - see SchemaValueSummary.
// ====

interface

uses
  System.SysUtils,
  SchemaNode;

const
  MaxInlineEnumValues = 6;

type
  TSchemaTypeText = class
  public
    class function Describe(ANode: TSchemaNode): string;
    class function DescribeWithDefault(ANode: TSchemaNode): string;
    class function EnumText(ANode: TSchemaNode): string;
    class function IsEnum(ANode: TSchemaNode): Boolean;
    // Short prose for an empty cell: "0 - 1", "1 or more", "true or false".
    // Describe is for readers of a shape; this is for someone about to type.
    class function HintText(ANode: TSchemaNode): string;
  end;

implementation

uses
  System.JSON,
  SchemaValueSummary;

{ ---- local helpers ---- }

function KindText(ANode: TSchemaNode): string;
begin
  if Trim(ANode.JsonType) <> '' then
    Exit(LowerCase(Trim(ANode.JsonType)));
  case ANode.Kind of
    skNull       : Result := 'null';
    skBoolean    : Result := 'bool';
    skInteger    : Result := 'int';
    skNumber     : Result := 'number';
    skString     : Result := 'string';
    skObject     : Result := 'object';
    skArray      : Result := 'array';
    skDictionary : Result := 'dictionary';
  else
    Result := 'any';
  end;
end;

function IsGeneratedTypeName(const ATypeName: string): Boolean;
begin
  // Generated names such as ".input.cohortPathsList.array" carry no information
  // a reader does not already get from the field name plus its kind.
  Result := (Pos('.', ATypeName) > 0);
end;

function NumText(AValue: Double): string;
begin
  Result := FloatToStr(AValue, TFormatSettings.Invariant);
end;

// "0..100", ">= 1", "<= 0.05" - the accepted range, so an editor does not have
// to guess what the field will take.
function BoundsText(ANode: TSchemaNode): string;
begin
  Result := '';
  if not (ANode.Kind in [skInteger, skNumber]) then
    Exit;
  if ANode.HasMinimum and ANode.HasMaximum then
    Result := Format('%s..%s', [NumText(ANode.Minimum), NumText(ANode.Maximum)])
  else if ANode.HasMinimum then
    Result := '>= ' + NumText(ANode.Minimum)
  else if ANode.HasMaximum then
    Result := '<= ' + NumText(ANode.Maximum);
end;

{ TSchemaTypeText }

class function TSchemaTypeText.IsEnum(ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode) and (ANode.EnumValues.Count > 0);
end;

class function TSchemaTypeText.EnumText(ANode: TSchemaNode): string;
var
  I     : Integer;
  Shown : Integer;
begin
  Result := '';
  if not IsEnum(ANode) then
    Exit;
  Shown := ANode.EnumValues.Count;
  if Shown > MaxInlineEnumValues then
    Shown := MaxInlineEnumValues;
  for I := 0 to Shown - 1 do
  begin
    if I > 0 then
      Result := Result + ' | ';
    Result := Result + ANode.EnumValues[I];
  end;
  if ANode.EnumValues.Count > Shown then
    Result := Result + Format(' | ... (%d)', [ANode.EnumValues.Count]);
  Result := Format('enum(%s)', [Result]);
end;

class function TSchemaTypeText.Describe(ANode: TSchemaNode): string;
var
  Items  : TSchemaNode;
  Bounds : string;
begin
  if not Assigned(ANode) then
    Exit('');

  if IsEnum(ANode) then
  begin
    Result := EnumText(ANode);
    if (ANode.TypeName <> '') and not IsGeneratedTypeName(ANode.TypeName) then
      Result := Format('%s %s', [ANode.TypeName, Result]);
    Exit;
  end;

  case ANode.Kind of
    skArray:
      begin
        Items := ANode.ItemsSchema;
        if Assigned(Items) then
          Result := Format('array<%s>', [Describe(Items)])
        else
          Result := 'array';
      end;
    skObject:
      begin
        if (ANode.TypeName <> '') and not IsGeneratedTypeName(ANode.TypeName) then
          Result := ANode.TypeName
        else if ANode.PropertyCount > 0 then
          Result := Format('object (%d fields)', [ANode.PropertyCount])
        else
          Result := 'object';
      end;
    skDictionary:
      Result := 'dictionary';
  else
    Result := KindText(ANode);
  end;

  if ANode.Nullable and (Result <> '') then
    Result := Result + '?';

  Bounds := BoundsText(ANode);
  if Bounds <> '' then
    Result := Trim(Result + ' ' + Bounds);
end;

class function TSchemaTypeText.HintText(ANode: TSchemaNode): string;
var
  I     : Integer;
  Shown : Integer;
begin
  Result := '';
  if not Assigned(ANode) then
    Exit;

  if IsEnum(ANode) then
  begin
    Shown := ANode.EnumValues.Count;
    if Shown > MaxInlineEnumValues then
      Shown := MaxInlineEnumValues;
    for I := 0 to Shown - 1 do
    begin
      if I > 0 then
        Result := Result + ', ';
      Result := Result + ANode.EnumValues[I];
    end;
    if ANode.EnumValues.Count > Shown then
      Result := Result + ', ...';
    Exit(Result);
  end;

  case ANode.Kind of
    skBoolean:
      Result := 'true or false';
    skInteger, skNumber:
      if ANode.HasMinimum and ANode.HasMaximum then
        Result := Format('%s - %s', [NumText(ANode.Minimum), NumText(ANode.Maximum)])
      else if ANode.HasMinimum then
        Result := NumText(ANode.Minimum) + ' or more'
      else if ANode.HasMaximum then
        Result := 'up to ' + NumText(ANode.Maximum)
      else if ANode.Kind = skInteger then
        Result := 'whole number'
      else
        Result := 'number';
    skString:
      Result := 'text';
    skArray:
      Result := 'list';
  end;

  // A real default is worth more than the range; a null default only restates
  // that the field is unset, which the blank cell already says.
  if Assigned(ANode.DefaultValue) and not (ANode.DefaultValue is TJSONNull) then
    Result := Trim(Format('%s (default %s)',
      [Result, TSchemaValueSummary.Describe(ANode, ANode.DefaultValue)]));
end;

class function TSchemaTypeText.DescribeWithDefault(ANode: TSchemaNode): string;
begin
  Result := Describe(ANode);
  if not Assigned(ANode) or not Assigned(ANode.DefaultValue) then
    Exit;
  if ANode.DefaultValue is TJSONNull then
    Exit;
  Result := Format('%s = %s',
    [Result, TSchemaValueSummary.Describe(ANode, ANode.DefaultValue)]);
end;

end.
