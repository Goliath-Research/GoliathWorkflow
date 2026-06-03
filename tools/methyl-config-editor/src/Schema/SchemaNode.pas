unit SchemaNode;

interface

uses
  System.Generics.Collections,
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
    FProperties: TObjectList<TSchemaProperty>;
    FOneOfBranches: TObjectList<TSchemaNode>;
    function GetPropertyCount: Integer;
    function GetProperty(Index: Integer): TSchemaProperty;
  public
    Kind: TSchemaKind;
    Title: string;
    Description: string;
    JsonType: string;
    Nullable: Boolean;
    ReadOnly: Boolean;
    Required: Boolean;
    EnumValues: TArray<string>;
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
    DiscriminatorMapping: TDictionary<string, string>;
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
    property OneOfBranches: TObjectList<TSchemaNode> read FOneOfBranches;
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
  FProperties := TObjectList<TSchemaProperty>.Create(True);
  FOneOfBranches := TObjectList<TSchemaNode>.Create(False);
  DiscriminatorMapping := TDictionary<string, string>.Create;
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
  DiscriminatorMapping.Free;
  FOneOfBranches.Free;
  if Assigned(DefaultValue) then
    DefaultValue.Free;
  FProperties.Free;
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
begin
  Result := TSchemaNode.Create;
  Result.Kind := Kind;
  Result.Title := Title;
  Result.Description := Description;
  Result.JsonType := JsonType;
  Result.Nullable := Nullable;
  Result.ReadOnly := ReadOnly;
  Result.Required := Required;
  Result.EnumValues := EnumValues;
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
