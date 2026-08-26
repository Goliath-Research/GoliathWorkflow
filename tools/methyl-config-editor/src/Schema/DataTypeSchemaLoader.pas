unit DataTypeSchemaLoader;

interface

uses
  Spring.Collections,
  System.SysUtils,
  SchemaNode;

type
  TDataTypeFieldInfo = record
    FieldName: string;
    FieldTypeName: string;
    FieldTypeKind: string;
    Required: Boolean;
  end;

  TDataTypeInfo = record
    Name: string;
    Kind: string;
    ElementTypeName: string;
    Fields: TArray<TDataTypeFieldInfo>;
    EnumValues: TArray<string>;
  end;

  TDataTypeFetchFn = reference to function(const AName: string;
    out Info: TDataTypeInfo): Boolean;

  TDataTypeSchemaLoader = class
  private
    FFetch: TDataTypeFetchFn;
    FOwned: IList<TSchemaNode>;
    FCache: IDictionary<string, TSchemaNode>;
    function CacheKey(const AName: string): string;
    function NewNode: TSchemaNode;
    function KindFromName(const AKind: string): TSchemaKind;
    function CopyForField(ATypeNode: TSchemaNode; const AFieldName: string;
      ARequired: Boolean): TSchemaNode;
    procedure ApplyKind(Node: TSchemaNode; const Info: TDataTypeInfo);
  public
    constructor Create(AFetch: TDataTypeFetchFn);
    destructor Destroy; override;
    procedure ClearCache;
    function Load(const AName: string): TSchemaNode;
  end;

implementation

constructor TDataTypeSchemaLoader.Create(AFetch: TDataTypeFetchFn);
begin
  inherited Create;
  FFetch := AFetch;
  FOwned := TCollections.CreateObjectList<TSchemaNode>(True);
  FCache := TCollections.CreateDictionary<string, TSchemaNode>;
end;

destructor TDataTypeSchemaLoader.Destroy;
begin
  FCache := nil;
  FOwned := nil;
  inherited Destroy;
end;

procedure TDataTypeSchemaLoader.ClearCache;
begin
  FCache.Clear;
  FOwned.Clear;
end;

function TDataTypeSchemaLoader.CacheKey(const AName: string): string;
begin
  Result := LowerCase(Trim(AName));
end;

function TDataTypeSchemaLoader.NewNode: TSchemaNode;
begin
  Result := TSchemaNode.Create;
  FOwned.Add(Result);
end;

function TDataTypeSchemaLoader.KindFromName(const AKind: string): TSchemaKind;
var
  Kind: string;
begin
  Kind := LowerCase(Trim(AKind));
  if (Kind = 'int') or (Kind = 'integer') then
    Exit(skInteger);
  if (Kind = 'bool') or (Kind = 'boolean') then
    Exit(skBoolean);
  if Kind = 'number' then
    Exit(skNumber);
  if Kind = 'object' then
    Exit(skObject);
  if Kind = 'array' then
    Exit(skArray);
  if Kind = 'null' then
    Exit(skNull);
  // string, datetime, bytes, any, enum
  Result := skString;
end;

procedure TDataTypeSchemaLoader.ApplyKind(Node: TSchemaNode; const Info: TDataTypeInfo);
var
  I: Integer;
begin
  Node.Title := Info.Name;
  Node.TypeName := Info.Name;
  Node.JsonType := Info.Kind;
  Node.Kind := KindFromName(Info.Kind);
  if SameText(Info.Kind, 'enum') then
    Node.Kind := skString;
  for I := 0 to Length(Info.EnumValues) - 1 do
    Node.EnumValues.Add(Info.EnumValues[I]);
end;

function TDataTypeSchemaLoader.CopyForField(ATypeNode: TSchemaNode;
  const AFieldName: string; ARequired: Boolean): TSchemaNode;
var
  I: Integer;
  E: string;
begin
  Result := NewNode;
  Result.Kind := ATypeNode.Kind;
  Result.Title := AFieldName;
  Result.Description := ATypeNode.Description;
  Result.JsonType := ATypeNode.JsonType;
  Result.TypeName := ATypeNode.TypeName;
  Result.Nullable := ATypeNode.Nullable;
  Result.ReadOnly := ATypeNode.ReadOnly;
  Result.Required := ARequired;
  for E in ATypeNode.EnumValues do
    Result.EnumValues.Add(E);
  Result.ItemsSchema := ATypeNode.ItemsSchema;
  Result.AdditionalPropertiesSchema := ATypeNode.AdditionalPropertiesSchema;
  Result.AdditionalPropertiesAllowed := ATypeNode.AdditionalPropertiesAllowed;
  Result.RefPath := ATypeNode.RefPath;
  Result.ResolvedFromRef := True;
  for I := 0 to ATypeNode.PropertyCount - 1 do
    Result.AddProperty(ATypeNode.Properties[I].Name,
      TSchemaNode(ATypeNode.Properties[I].Node));
end;

function TDataTypeSchemaLoader.Load(const AName: string): TSchemaNode;
var
  Key: string;
  Info: TDataTypeInfo;
  I: Integer;
  Child: TSchemaNode;
  PropNode: TSchemaNode;
begin
  Result := nil;
  Key := CacheKey(AName);
  if Key = '' then
    Exit;
  if FCache.TryGetValue(Key, Result) then
    Exit;

  if not Assigned(FFetch) or not FFetch(AName, Info) then
    Exit;

  Result := NewNode;
  FCache.Add(Key, Result);

  ApplyKind(Result, Info);

  if Result.Kind = skArray then
  begin
    if Trim(Info.ElementTypeName) <> '' then
      Result.ItemsSchema := Load(Info.ElementTypeName);
    Exit;
  end;

  if Result.Kind <> skObject then
    Exit;

  for I := 0 to Length(Info.Fields) - 1 do
  begin
    if Trim(Info.Fields[I].FieldTypeName) = '' then
      Child := nil
    else
      Child := Load(Info.Fields[I].FieldTypeName);
    if not Assigned(Child) then
    begin
      Child := NewNode;
      Child.Kind := KindFromName(Info.Fields[I].FieldTypeKind);
      Child.Title := Info.Fields[I].FieldName;
      Child.JsonType := Info.Fields[I].FieldTypeKind;
      Child.TypeName := Info.Fields[I].FieldTypeName;
      Child.Required := Info.Fields[I].Required;
      Result.AddProperty(Info.Fields[I].FieldName, Child);
      Continue;
    end;
    if Child = Result then
      PropNode := Child
    else
      PropNode := CopyForField(Child, Info.Fields[I].FieldName, Info.Fields[I].Required);
    Result.AddProperty(Info.Fields[I].FieldName, PropNode);
  end;
end;

end.
