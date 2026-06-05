unit SchemaPropertyGrid;

interface

uses
  System.Classes,
  System.JSON,
  System.SysUtils,
  Spring.Collections,
  uniGUIApplication,
  uniGUIDialogs,
  uniGUITypes,
  uniPropertyGrid,
  SchemaNode,
  SchemaBranchResolver,
  SchemaDictionaryResolver,
  SchemaValidator,
  SchemaValueSummary,
  JsonValueParsing;

type
  TGridPropertyMeta = class
  public
    GridLabel: string;
    PropertyName: string;
    DisplayName: string;
    SchemaNode: TSchemaNode;
    IsComplex: Boolean;
    IsDiscriminator: Boolean;
  end;

  TSchemaPropertyGridController = class
  private
    FGrid: TUniPropertyGrid;
    FSchema: TSchemaNode;
    FWorking: TJSONObject;
    FRows: IList<TGridPropertyMeta>;
    FOnRebuild: TNotifyEvent;
    FOnOpenComplex: TNotifyEvent;
    FPendingComplexRow: TGridPropertyMeta;
    procedure ClearRows;
    function UsesDictionaryLayout(ANode: TSchemaNode): Boolean;
    procedure AddDiscriminatorRow;
    procedure AddDictionaryRows;
    procedure AddPropertyRows(EffectiveSchema: TSchemaNode);
    function DisplayTitle(ANode: TSchemaNode; const PropName: string): string;
    function GetPropertyValue(const PropName: string): TJSONValue;
    procedure SetPropertyValue(const PropName: string; AValue: TJSONValue);
    procedure ClearPropertyValue(const PropName: string);
    procedure AddRowMeta(const PropName, DisplayName: string; ANode: TSchemaNode;
      IsComplex, IsDiscriminator: Boolean);
    procedure AddGridProperty(ARow: TGridPropertyMeta);
    function FindRowMeta(const PropName: string): TGridPropertyMeta;
    procedure HandleDiscriminatorChange(ARow: TGridPropertyMeta; const PropValue: string);
    procedure HandleScalarChange(ARow: TGridPropertyMeta; const PropValue: string;
      var Handled: Boolean);
    procedure HandleComplexOpen(ARow: TGridPropertyMeta; var Handled: Boolean);
  public
    constructor Create(AGrid: TUniPropertyGrid);
    destructor Destroy; override;
    procedure Bind(const ASchema: TSchemaNode; AWorking: TJSONObject);
    procedure Populate;
    function ValidateAll(out ErrorMessage: string): Boolean;
    function ChildBreadcrumb(const ASegment: string; const ABreadcrumb: string): string;
    property Working: TJSONObject read FWorking;
    property Schema: TSchemaNode read FSchema;
    property PendingComplexRow: TGridPropertyMeta read FPendingComplexRow;
    property OnRebuild: TNotifyEvent read FOnRebuild write FOnRebuild;
    property OnOpenComplex: TNotifyEvent read FOnOpenComplex write FOnOpenComplex;
    procedure PropertyChange(Sender: TObject; const PropName, PropValue: string;
      var Handled: Boolean);
    procedure ApplyComplexEdit(const PropName: string; AValue: TJSONValue);
  end;

implementation

type
  TUniPropertyGridAccess = class(TUniPropertyGrid);

constructor TSchemaPropertyGridController.Create(AGrid: TUniPropertyGrid);
begin
  inherited Create;
  FGrid := AGrid;
  FRows := TCollections.CreateObjectList<TGridPropertyMeta>(True);
end;

destructor TSchemaPropertyGridController.Destroy;
begin
  FRows := nil;
  inherited;
end;

procedure TSchemaPropertyGridController.Bind(const ASchema: TSchemaNode;
  AWorking: TJSONObject);
begin
  FSchema := ASchema;
  FWorking := AWorking;
end;

function TSchemaPropertyGridController.ChildBreadcrumb(const ASegment,
  ABreadcrumb: string): string;
begin
  if ABreadcrumb = '' then
    Exit(ASegment);
  Result := ABreadcrumb + ' / ' + ASegment;
end;

procedure TSchemaPropertyGridController.ClearRows;
begin
  FRows.Clear;
  if Assigned(FGrid) then
    FGrid.Clear;
end;

function TSchemaPropertyGridController.UsesDictionaryLayout(
  ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode) and (
    (ANode.Kind = skDictionary) or
    ((ANode.Kind = skObject) and (ANode.PropertyCount = 0) and
      ANode.AdditionalPropertiesAllowed));
end;

function TSchemaPropertyGridController.DisplayTitle(ANode: TSchemaNode;
  const PropName: string): string;
begin
  if Assigned(ANode) and (ANode.Title <> '') then
    Exit(ANode.Title);
  Result := PropName;
end;

procedure TSchemaPropertyGridController.AddRowMeta(const PropName, DisplayName: string;
  ANode: TSchemaNode; IsComplex, IsDiscriminator: Boolean);
var
  Row: TGridPropertyMeta;
begin
  Row := TGridPropertyMeta.Create;
  Row.PropertyName := PropName;
  Row.DisplayName := DisplayName;
  Row.SchemaNode := ANode;
  Row.IsComplex := IsComplex;
  Row.IsDiscriminator := IsDiscriminator;
  FRows.Add(Row);
end;

procedure TSchemaPropertyGridController.AddGridProperty(ARow: TGridPropertyMeta);
var
  Val: TJSONValue;
  DisplayValue: string;
  CaptionText: string;
begin
  Val := GetPropertyValue(ARow.PropertyName);
  DisplayValue := TJsonValueParsing.ValueToGridString(ARow.SchemaNode, Val);
  CaptionText := ARow.DisplayName;
  if Assigned(ARow.SchemaNode) and ARow.SchemaNode.Required then
    CaptionText := CaptionText + ' *';
  ARow.GridLabel := CaptionText;
  FGrid.AddProperty([ARow.GridLabel, DisplayValue]);
end;

procedure TSchemaPropertyGridController.AddDiscriminatorRow;
var
  Key: string;
  Val: TJSONValue;
  Current: string;
  Row: TGridPropertyMeta;
begin
  if (FSchema.DiscriminatorProperty = '') or (FSchema.DiscriminatorMapping.Count = 0) then
    Exit;
  Row := TGridPropertyMeta.Create;
  Row.PropertyName := FSchema.DiscriminatorProperty;
  Row.DisplayName := FSchema.DiscriminatorProperty;
  Row.SchemaNode := FSchema;
  Row.IsComplex := False;
  Row.IsDiscriminator := True;
  FRows.Add(Row);
  Val := GetPropertyValue(FSchema.DiscriminatorProperty);
  if Val is TJSONString then
    Current := TJSONString(Val).Value
  else
  begin
    Current := '';
    for Key in FSchema.DiscriminatorMapping.Keys do
    begin
      Current := Key;
      Break;
    end;
  end;
  Row.GridLabel := Row.DisplayName + ' *';
  FGrid.AddProperty([Row.GridLabel, Current]);
end;

procedure TSchemaPropertyGridController.AddDictionaryRows;
var
  Pair: TJSONPair;
  Key: string;
  EntrySchema: TSchemaNode;
  IsComplex: Boolean;
begin
  for Pair in FWorking do
  begin
    Key := Pair.JsonString.Value;
    if not TSchemaDictionaryResolver.TryResolveEntrySchema(FSchema, Key, EntrySchema) then
      EntrySchema := TSchemaDictionaryResolver.BaseValueSchema(FSchema);
    IsComplex := TJsonValueParsing.IsComplexKind(EntrySchema);
    AddRowMeta(Key, Key, EntrySchema, IsComplex, False);
    AddGridProperty(FRows.Last);
  end;
end;

procedure TSchemaPropertyGridController.AddPropertyRows(EffectiveSchema: TSchemaNode);
var
  Prop: TSchemaProperty;
  PropNode: TSchemaNode;
  IsComplex: Boolean;
begin
  for Prop in EffectiveSchema.PropertyItems do
  begin
    if (FSchema.DiscriminatorProperty <> '') and
      SameText(Prop.Name, FSchema.DiscriminatorProperty) then
      Continue;
    PropNode := TSchemaNode(Prop.Node);
    IsComplex := TJsonValueParsing.IsComplexKind(PropNode);
    AddRowMeta(Prop.Name, DisplayTitle(PropNode, Prop.Name), PropNode, IsComplex, False);
    AddGridProperty(FRows.Last);
  end;
end;

procedure TSchemaPropertyGridController.Populate;
var
  Effective: TSchemaNode;
begin
  ClearRows;
  if not Assigned(FSchema) or not Assigned(FWorking) then
    Exit;
  Effective := TSchemaBranchResolver.ResolveObjectSchema(FSchema, FWorking);
  if FSchema.OneOfBranches.Count > 0 then
    AddDiscriminatorRow;
  if UsesDictionaryLayout(Effective) then
    AddDictionaryRows
  else
    AddPropertyRows(Effective);
  TUniPropertyGridAccess(FGrid).PopulateGrid;
end;

function TSchemaPropertyGridController.GetPropertyValue(const PropName: string): TJSONValue;
begin
  Result := FWorking.GetValue(PropName);
end;

procedure TSchemaPropertyGridController.SetPropertyValue(const PropName: string;
  AValue: TJSONValue);
var
  Existing: TJSONPair;
begin
  Existing := FWorking.RemovePair(PropName);
  if Assigned(Existing) then
    Existing.Free;
  if Assigned(AValue) then
    FWorking.AddPair(PropName, AValue);
end;

procedure TSchemaPropertyGridController.ClearPropertyValue(const PropName: string);
var
  Existing: TJSONPair;
begin
  Existing := FWorking.RemovePair(PropName);
  if Assigned(Existing) then
    Existing.Free;
end;

function TSchemaPropertyGridController.FindRowMeta(const PropName: string): TGridPropertyMeta;
var
  Row: TGridPropertyMeta;
begin
  Result := nil;
  for Row in FRows do
    if SameText(Row.GridLabel, PropName) or SameText(Row.PropertyName, PropName) then
      Exit(Row);
end;

procedure TSchemaPropertyGridController.HandleDiscriminatorChange(
  ARow: TGridPropertyMeta; const PropValue: string);
var
  Key: string;
  Found: Boolean;
begin
  if Trim(PropValue) = '' then
  begin
    ClearPropertyValue(ARow.PropertyName);
    Populate;
    Exit;
  end;
  Found := False;
  for Key in FSchema.DiscriminatorMapping.Keys do
    if SameText(Key, Trim(PropValue)) then
    begin
      Found := True;
      SetPropertyValue(ARow.PropertyName, TJSONString.Create(Key));
      Break;
    end;
  if not Found then
  begin
    MessageDlg('Invalid discriminator value.', mtWarning, [mbOK]);
    Exit;
  end;
  Populate;
  if Assigned(FOnRebuild) then
    FOnRebuild(Self);
end;

procedure TSchemaPropertyGridController.HandleScalarChange(ARow: TGridPropertyMeta;
  const PropValue: string; var Handled: Boolean);
var
  Parsed: TJSONValue;
  Err: string;
begin
  if not TJsonValueParsing.ParseGridString(ARow.SchemaNode, PropValue, Parsed, Err) then
  begin
    Handled := True;
    MessageDlg(Format('%s: %s', [ARow.DisplayName, Err]), mtWarning, [mbOK]);
    Exit;
  end;
  try
    if not TSchemaValidator.ValidateValue(ARow.SchemaNode, Parsed, Err) then
    begin
      Handled := True;
      MessageDlg(Format('%s: %s', [ARow.DisplayName, Err]), mtWarning, [mbOK]);
      Exit;
    end;
    SetPropertyValue(ARow.PropertyName, Parsed.Clone as TJSONValue);
    Handled := True;
  finally
    Parsed.Free;
  end;
end;

procedure TSchemaPropertyGridController.HandleComplexOpen(ARow: TGridPropertyMeta;
  var Handled: Boolean);
begin
  FPendingComplexRow := ARow;
  Handled := True;
  if Assigned(FOnOpenComplex) then
    FOnOpenComplex(Self);
end;

procedure TSchemaPropertyGridController.PropertyChange(Sender: TObject;
  const PropName, PropValue: string; var Handled: Boolean);
var
  Row: TGridPropertyMeta;
begin
  Row := FindRowMeta(PropName);
  if not Assigned(Row) then
    Exit;
  if Row.IsComplex or TJsonValueParsing.IsComplexGridValue(PropValue) then
  begin
    HandleComplexOpen(Row, Handled);
    Exit;
  end;
  if Row.IsDiscriminator then
  begin
    Handled := True;
    HandleDiscriminatorChange(Row, PropValue);
    Exit;
  end;
  HandleScalarChange(Row, PropValue, Handled);
end;

procedure TSchemaPropertyGridController.ApplyComplexEdit(const PropName: string;
  AValue: TJSONValue);
begin
  if Assigned(AValue) then
    SetPropertyValue(PropName, AValue.Clone as TJSONValue)
  else if Assigned(FSchema) and FSchema.Nullable then
    SetPropertyValue(PropName, TJSONNull.Create)
  else
    ClearPropertyValue(PropName);
  Populate;
end;

function TSchemaPropertyGridController.ValidateAll(out ErrorMessage: string): Boolean;
var
  Row: TGridPropertyMeta;
  Val: TJSONValue;
begin
  for Row in FRows do
  begin
    if Row.PropertyName = '' then
      Continue;
    Val := GetPropertyValue(Row.PropertyName);
    if not TSchemaValidator.ValidateValue(Row.SchemaNode, Val, ErrorMessage) then
    begin
      ErrorMessage := Format('%s: %s', [Row.DisplayName, ErrorMessage]);
      Exit(False);
    end;
  end;
  Result := TSchemaValidator.ValidateObject(FSchema, FWorking, ErrorMessage);
end;

end.
