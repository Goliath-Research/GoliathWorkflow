unit SchemaNode;

interface

uses
  Spring.Collections,
  System.JSON,
  System.SysUtils;

type
  TSchemaKind = (
    skUnknown,
    skNull,
    skBoolean,
    skInteger,
    skNumber,
    skString,
    skObject,
    skArray,
    skDictionary
  );

  TSchemaProperty = class
  public
    Name: string;
    Node: TObject; // TSchemaNode - forward ref avoided in interface uses
    constructor Create(const AName: string; ANode: TObject);
  end;

  TSchemaNode = class
  private
    FProperties: IList<TSchemaProperty>;
    FOneOfBranches: IList<TSchemaNode>;
    function GetPropertyCount: Integer;
    function GetProperty(Index: Integer): TSchemaProperty;
  public
    Kind: TSchemaKind;
    Title: string;
    Description: string;
    JsonType: string;
    TypeName: string; // catalog / $ref name; Title is the field caption
    Nullable: Boolean;
    ReadOnly: Boolean;
    Required: Boolean;
    EnumValues: IList<string>;
    DefaultValue: TJSONValue;
    MinLength: Integer;
    MaxLength: Integer;
    Minimum: Double;
    Maximum: Double;
    HasMinimum: Boolean;
    HasMaximum: Boolean;
    ItemsSchema: TSchemaNode;
    AdditionalPropertiesSchema: TSchemaNode;
    AdditionalPropertiesAllowed: Boolean;
    RefPath: string;
    DiscriminatorProperty: string;
    DiscriminatorMapping: IDictionary<string, string>;
    ResolvedFromRef: Boolean;
    constructor Create;
    destructor Destroy; override;
    procedure AddProperty(const AName: string; ANode: TSchemaNode);
    procedure AddOneOfBranch(ABranch: TSchemaNode);
    function FindProperty(const AName: string): TSchemaProperty;
    function IsScalar: Boolean;
    function IsComplex: Boolean;
    function CloneShallow: TSchemaNode;
    property PropertyCount: Integer read GetPropertyCount;
    property Properties[Index: Integer]: TSchemaProperty read GetProperty;
    property PropertyItems: IList<TSchemaProperty> read FProperties;
    property OneOfBranches: IList<TSchemaNode> read FOneOfBranches;
  end;

implementation

constructor TSchemaProperty.Create(const AName: string; ANode: TObject);
begin
  inherited Create;
  Name := AName;
  Node := ANode;
end;

constructor TSchemaNode.Create;
begin
  inherited Create;
  FProperties := TCollections.CreateObjectList<TSchemaProperty>(True);
  FOneOfBranches := TCollections.CreateObjectList<TSchemaNode>(False);
  DiscriminatorMapping := TCollections.CreateDictionary<string, string>;
  EnumValues := TCollections.CreateList<string>;
  Kind := skUnknown;
  MinLength := -1;
  MaxLength := -1;
  HasMinimum := False;
  HasMaximum := False;
  AdditionalPropertiesAllowed := False;
  ResolvedFromRef := False;
end;

destructor TSchemaNode.Destroy;
begin
  if Assigned(DefaultValue) then
    DefaultValue.Free;
  FProperties := nil;
  FOneOfBranches := nil;
  DiscriminatorMapping := nil;
  EnumValues := nil;
  inherited Destroy;
end;

procedure TSchemaNode.AddProperty(const AName: string; ANode: TSchemaNode);
begin
  FProperties.Add(TSchemaProperty.Create(AName, ANode));
end;

procedure TSchemaNode.AddOneOfBranch(ABranch: TSchemaNode);
begin
  FOneOfBranches.Add(ABranch);
end;

function TSchemaNode.FindProperty(const AName: string): TSchemaProperty;
var
  Prop: TSchemaProperty;
begin
  Result := nil;
  for Prop in FProperties do
    if SameText(Prop.Name, AName) then
      Exit(Prop);
end;

function TSchemaNode.GetProperty(Index: Integer): TSchemaProperty;
begin
  Result := FProperties[Index];
end;

function TSchemaNode.GetPropertyCount: Integer;
begin
  Result := FProperties.Count;
end;

function TSchemaNode.IsScalar: Boolean;
begin
  Result := Kind in [skBoolean, skInteger, skNumber, skString, skNull];
end;

function TSchemaNode.IsComplex: Boolean;
begin
  Result := Kind in [skObject, skArray, skDictionary];
end;

function TSchemaNode.CloneShallow: TSchemaNode;
var
  E: string;
begin
  Result := TSchemaNode.Create;
  Result.Kind := Kind;
  Result.Title := Title;
  Result.Description := Description;
  Result.JsonType := JsonType;
  Result.TypeName := TypeName;
  Result.Nullable := Nullable;
  Result.ReadOnly := ReadOnly;
  Result.Required := Required;
  for E in EnumValues do
    Result.EnumValues.Add(E);
  if Assigned(DefaultValue) then
    Result.DefaultValue := DefaultValue.Clone as TJSONValue;
  Result.MinLength := MinLength;
  Result.MaxLength := MaxLength;
  Result.Minimum := Minimum;
  Result.Maximum := Maximum;
  Result.HasMinimum := HasMinimum;
  Result.HasMaximum := HasMaximum;
  Result.RefPath := RefPath;
  Result.DiscriminatorProperty := DiscriminatorProperty;
  Result.AdditionalPropertiesAllowed := AdditionalPropertiesAllowed;
  Result.ResolvedFromRef := ResolvedFromRef;
  if Assigned(ItemsSchema) then
    Result.ItemsSchema := ItemsSchema.CloneShallow;
  if Assigned(AdditionalPropertiesSchema) then
    Result.AdditionalPropertiesSchema := AdditionalPropertiesSchema.CloneShallow;
end;

end.
