unit SchemaDictionaryResolver;

interface

uses
  SchemaNode;

type
  TSchemaDictionaryResolver = class
  private
    class var FStringFallback: TSchemaNode;
    class constructor Create;
    class destructor Destroy;
  public
    class function IsRegistryResolutionRequired(ASchema: TSchemaNode): Boolean; static;
    class function BaseValueSchema(ContainerSchema: TSchemaNode): TSchemaNode; static;
    class function TryResolveEntrySchema(ContainerSchema: TSchemaNode;
      const Key: string; out EntrySchema: TSchemaNode): Boolean; static;
  end;

implementation

uses
  SchemaCatalog;

class constructor TSchemaDictionaryResolver.Create;
begin
  FStringFallback := nil;
end;

class destructor TSchemaDictionaryResolver.Destroy;
begin
  FStringFallback.Free;
  FStringFallback := nil;
end;

class function TSchemaDictionaryResolver.BaseValueSchema(
  ContainerSchema: TSchemaNode): TSchemaNode;
begin
  if Assigned(ContainerSchema) and Assigned(ContainerSchema.AdditionalPropertiesSchema) then
    Exit(ContainerSchema.AdditionalPropertiesSchema);
  if not Assigned(FStringFallback) then
  begin
    FStringFallback := TSchemaNode.Create;
    FStringFallback.Kind := skString;
  end;
  Result := FStringFallback;
end;

class function TSchemaDictionaryResolver.IsRegistryResolutionRequired(
  ASchema: TSchemaNode): Boolean;
begin
  if not Assigned(ASchema) then
    Exit(True);
  if ASchema.Kind = skUnknown then
    Exit(True);
  Result := (ASchema.Kind in [skObject, skDictionary]) and
    (ASchema.PropertyCount = 0) and ASchema.AdditionalPropertiesAllowed and
    ((not Assigned(ASchema.AdditionalPropertiesSchema)) or
      (ASchema.AdditionalPropertiesSchema.Kind = skUnknown));
end;

class function TSchemaDictionaryResolver.TryResolveEntrySchema(
  ContainerSchema: TSchemaNode; const Key: string;
  out EntrySchema: TSchemaNode): Boolean;
var
  Catalog: TSchemaCatalog;
  BaseSchema: TSchemaNode;
begin
  BaseSchema := BaseValueSchema(ContainerSchema);
  if not IsRegistryResolutionRequired(BaseSchema) then
  begin
    EntrySchema := BaseSchema;
    Exit(Assigned(EntrySchema));
  end;

  EntrySchema := nil;
  Catalog := TSchemaCatalog.Current;
  Result := Assigned(Catalog) and Catalog.TryResolveSchema(Key, EntrySchema) and
    Assigned(EntrySchema);
end;

end.
