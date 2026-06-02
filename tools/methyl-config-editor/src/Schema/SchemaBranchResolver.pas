unit SchemaBranchResolver;

interface

uses
  System.JSON,
  System.SysUtils,
  SchemaNode;

type
  TSchemaBranchResolver = class
  public
    class function ResolveObjectSchema(ANode: TSchemaNode;
      AObject: TJSONObject): TSchemaNode;
    class function ResolveBranchByDiscriminator(ANode: TSchemaNode;
      const DiscriminatorValue: string): TSchemaNode;
  end;

implementation

uses
  JsonSchemaLoader;

class function TSchemaBranchResolver.ResolveBranchByDiscriminator(
  ANode: TSchemaNode; const DiscriminatorValue: string): TSchemaNode;
var
  RefPath: string;
  I: Integer;
  Branch: TSchemaNode;
begin
  Result := ANode;
  if not Assigned(ANode) then
    Exit;
  if ANode.OneOfBranches.Count = 0 then
    Exit;
  if (ANode.DiscriminatorProperty <> '') and
    ANode.DiscriminatorMapping.TryGetValue(DiscriminatorValue, RefPath) then
  begin
    for I := 0 to ANode.OneOfBranches.Count - 1 do
    begin
      Branch := ANode.OneOfBranches[I];
      if SameText(Branch.RefPath, RefPath) then
        Exit(Branch);
    end;
  end;
  for I := 0 to ANode.OneOfBranches.Count - 1 do
  begin
    Branch := ANode.OneOfBranches[I];
    if Branch.FindProperty(ANode.DiscriminatorProperty) <> nil then
      Exit(Branch);
  end;
  if ANode.OneOfBranches.Count > 0 then
    Result := ANode.OneOfBranches[0];
end;

class function TSchemaBranchResolver.ResolveObjectSchema(ANode: TSchemaNode;
  AObject: TJSONObject): TSchemaNode;
var
  DiscVal: TJSONValue;
  DiscStr: string;
begin
  Result := ANode;
  if not Assigned(ANode) or not Assigned(AObject) then
    Exit;
  if ANode.OneOfBranches.Count = 0 then
    Exit;
  if ANode.DiscriminatorProperty = '' then
  begin
    if ANode.OneOfBranches.Count > 0 then
      Result := ANode.OneOfBranches[0];
    Exit;
  end;
  DiscVal := AObject.GetValue(ANode.DiscriminatorProperty);
  if DiscVal is TJSONString then
    DiscStr := TJSONString(DiscVal).Value
  else
    DiscStr := '';
  Result := ResolveBranchByDiscriminator(ANode, DiscStr);
end;

end.
