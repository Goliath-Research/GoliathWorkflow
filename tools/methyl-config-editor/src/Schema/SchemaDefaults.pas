unit SchemaDefaults;

interface

uses
  System.JSON,
  SchemaNode;

type
  TSchemaDefaults = class
  public
    class function CreateDefaultValue(ANode: TSchemaNode): TJSONValue;
    class function CreateDefaultObject(ANode: TSchemaNode): TJSONObject;
  end;

implementation

uses
  System.SysUtils;

class function TSchemaDefaults.CreateDefaultValue(ANode: TSchemaNode): TJSONValue;
var
  Arr: TJSONArray;
begin
  if not Assigned(ANode) then
    Exit(TJSONNull.Create);
  if Assigned(ANode.DefaultValue) then
    Exit(ANode.DefaultValue.Clone as TJSONValue);
  if ANode.Nullable then
    Exit(TJSONNull.Create);
  case ANode.Kind of
    skBoolean:
      Exit(TJSONFalse.Create);
    skInteger:
      Exit(TJSONNumber.Create(0));
    skNumber:
      Exit(TJSONNumber.Create(0));
    skString:
      if ANode.EnumValues.Count > 0 then
        Exit(TJSONString.Create(ANode.EnumValues[0]))
      else
        Exit(TJSONString.Create(''));
    skObject, skDictionary:
      Exit(CreateDefaultObject(ANode));
    skArray:
      begin
        Arr := TJSONArray.Create;
        Exit(Arr);
      end;
  else
    Exit(TJSONNull.Create);
  end;
end;

class function TSchemaDefaults.CreateDefaultObject(ANode: TSchemaNode): TJSONObject;
var
  I: Integer;
  Prop: TSchemaProperty;
  PropNode: TSchemaNode;
  Branch: TSchemaNode;
  Key: string;
begin
  Result := TJSONObject.Create;
  if not Assigned(ANode) then
    Exit;
  if ANode.OneOfBranches.Count > 0 then
  begin
    Branch := ANode.OneOfBranches[0];
    for I := 0 to Branch.PropertyCount - 1 do
    begin
      Prop := Branch.Properties[I];
      PropNode := TSchemaNode(Prop.Node);
      if PropNode.Required or Assigned(PropNode.DefaultValue) then
        Result.AddPair(Prop.Name, CreateDefaultValue(PropNode));
    end;
    if ANode.DiscriminatorProperty <> '' then
    begin
      for Key in ANode.DiscriminatorMapping.Keys do
      begin
        Result.AddPair(ANode.DiscriminatorProperty, TJSONString.Create(Key));
        Break;
      end;
    end;
    Exit;
  end;
  for I := 0 to ANode.PropertyCount - 1 do
  begin
    Prop := ANode.Properties[I];
    PropNode := TSchemaNode(Prop.Node);
    if PropNode.Required or Assigned(PropNode.DefaultValue) then
      Result.AddPair(Prop.Name, CreateDefaultValue(PropNode));
  end;
end;

end.
