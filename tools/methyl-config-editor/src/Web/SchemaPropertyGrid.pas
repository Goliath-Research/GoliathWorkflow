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
  JsonPath,
  SchemaNode,
  SchemaBranchResolver,
  SchemaDictionaryResolver,
  SchemaTypeText,
  SchemaValidator,
  SchemaValueSummary,
  JsonValueParsing;

type
  TGridPropertyMeta = class
  public
    GridLabel       : string;
    GridKey         : string;   // JS-identifier-safe; what the widget receives
    PropertyName    : string;
    DisplayName     : string;
    Path            : string;
    SchemaNode      : TSchemaNode;
    IsComplex       : Boolean;
    IsDiscriminator : Boolean;
  end;

  TSchemaPropertyGridController = class
  private
    FGrid              : TUniPropertyGrid;
    FSchema            : TSchemaNode;
    FWorking           : TJSONObject;
    FRows              : IList<TGridPropertyMeta>;
    FOnRebuild         : TNotifyEvent;
    FOnOpenComplex     : TNotifyEvent;
    FPendingComplexRow : TGridPropertyMeta;
    FShowTypeInLabel   : Boolean;
    FReadOnly          : Boolean;
    FShowOnlyPresent   : Boolean;
    FFlattenObjects    : Boolean;
    FDefaultsSchema    : TSchemaNode;
    procedure ClearRows;
    function  UsesDictionaryLayout(ANode: TSchemaNode): Boolean;
    function  ShouldFlatten(ANode: TSchemaNode): Boolean;
    procedure AddDiscriminatorRow;
    procedure AddDictionaryRows;
    procedure AddPropertyRows(EffectiveSchema: TSchemaNode; const APathPrefix: string);
    function  DisplayTitle(ANode: TSchemaNode; const PropName: string): string;
    function  GetPropertyValue(const APath: string): TJSONValue;
    procedure SetPropertyValue(const APath: string; AValue: TJSONValue);
    procedure ClearPropertyValue(const APath: string);
    procedure AddRowMeta(const APath, APropName, ADisplayName: string;
      ANode: TSchemaNode; IsComplex, IsDiscriminator: Boolean);
    procedure AddGridProperty(ARow: TGridPropertyMeta);
    function  UniqueGridKey(ARow: TGridPropertyMeta; const ACaption: string): string;
    function  FindRowMeta(const PropName: string): TGridPropertyMeta;
    function  SchemaAtPath(ARoot: TSchemaNode; const APath: string): TSchemaNode;
    function  DisplayValueFor(ARow: TGridPropertyMeta): string;
    procedure HandleDiscriminatorChange(ARow: TGridPropertyMeta; const PropValue: string);
    procedure HandleScalarChange(ARow: TGridPropertyMeta; const PropValue: string;
      var Handled: Boolean);
    procedure HandleComplexOpen(ARow: TGridPropertyMeta; var Handled: Boolean);
  public
    constructor Create(AGrid: TUniPropertyGrid);
    destructor Destroy; override;
    procedure Bind(const ASchema: TSchemaNode; AWorking: TJSONObject);
    procedure Populate;
    function  ValidateAll(out ErrorMessage: string): Boolean;
    function  ChildBreadcrumb(const ASegment: string; const ABreadcrumb: string): string;
    function  RowValue(ARow: TGridPropertyMeta): TJSONValue;
    property Working: TJSONObject read FWorking;
    property Schema: TSchemaNode read FSchema;
    property PendingComplexRow: TGridPropertyMeta read FPendingComplexRow;
    property OnRebuild: TNotifyEvent read FOnRebuild write FOnRebuild;
    property OnOpenComplex: TNotifyEvent read FOnOpenComplex write FOnOpenComplex;
    property ShowTypeInLabel: Boolean read FShowTypeInLabel write FShowTypeInLabel;
    property ReadOnly: Boolean read FReadOnly write FReadOnly;
    property ShowOnlyPresent: Boolean read FShowOnlyPresent write FShowOnlyPresent;
    property FlattenObjects: Boolean read FFlattenObjects write FFlattenObjects;
    property DefaultsSchema: TSchemaNode read FDefaultsSchema write FDefaultsSchema;
    procedure PropertyChange(Sender: TObject; const PropName, PropValue: string;
      var Handled: Boolean);
    procedure ApplyComplexEdit(const APath: string; AValue: TJSONValue);
  end;

implementation

type
  TUniPropertyGridAccess = class(TUniPropertyGrid);

{ ---- local helpers ---- }

// TUniPropertyGrid.GetJson pastes every row name straight into a JS object
// literal ("Name:Value") and only quotes it when the name carries a '-'. A
// caption holding a space or the ' / ' flatten separator therefore emits
// `alignment_guardrails / enabled:"False"`, the callback script dies with a
// SyntaxError, and uniGUI shows the raw script in an error window instead of
// the tab. Feed the widget an identifier; the caption lives on in GridLabel.
function JsSafeKey(const ACaption: string): string;
var
  Ch : Char;
begin
  Result := '';
  for Ch in ACaption do
    if CharInSet(Ch, ['A'..'Z', 'a'..'z', '0'..'9', '_', '$']) then
      Result := Result + Ch
    else if (Result <> '') and (Result[Length(Result)] <> '_') then
      Result := Result + '_';
  while (Result <> '') and (Result[Length(Result)] = '_') do
    SetLength(Result, Length(Result) - 1);
  if Result = '' then
    Result := '_';
  if CharInSet(Result[1], ['0'..'9']) then
    Result := '_' + Result;
end;

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

procedure TSchemaPropertyGridController.AddRowMeta(const APath, APropName,
  ADisplayName: string; ANode: TSchemaNode; IsComplex, IsDiscriminator: Boolean);
var
  Row: TGridPropertyMeta;
begin
  Row := TGridPropertyMeta.Create;
  Row.Path := APath;
  Row.PropertyName := APropName;
  Row.DisplayName := ADisplayName;
  Row.SchemaNode := ANode;
  Row.IsComplex := IsComplex;
  Row.IsDiscriminator := IsDiscriminator;
  FRows.Add(Row);
end;

function TSchemaPropertyGridController.ShouldFlatten(ANode: TSchemaNode): Boolean;
begin
  Result := FFlattenObjects and Assigned(ANode) and (ANode.Kind = skObject)
    and (ANode.PropertyCount > 0) and (ANode.OneOfBranches.Count = 0);
end;

function TSchemaPropertyGridController.SchemaAtPath(ARoot: TSchemaNode;
  const APath: string): TSchemaNode;
var
  Segments: IList<string>;
  I: Integer;
  Prop: TSchemaProperty;
begin
  Result := ARoot;
  if not Assigned(Result) then
    Exit;
  Segments := TJsonPath.SplitPath(APath);
  for I := 0 to Segments.Count - 1 do
  begin
    Prop := Result.FindProperty(Segments[I]);
    if not Assigned(Prop) then
      Exit(nil);
    Result := TSchemaNode(Prop.Node);
    if not Assigned(Result) then
      Exit;
  end;
end;

function TSchemaPropertyGridController.DisplayValueFor(ARow: TGridPropertyMeta): string;
var
  Val     : TJSONValue;
  DefNode : TSchemaNode;
begin
  Val := GetPropertyValue(ARow.Path);
  if Assigned(Val) then
    Exit(TJsonValueParsing.ValueToGridString(ARow.SchemaNode, Val));
  if Assigned(FDefaultsSchema) then
  begin
    DefNode := SchemaAtPath(FDefaultsSchema, ARow.Path);
    if Assigned(DefNode) and Assigned(DefNode.DefaultValue) then
      Exit(TJsonValueParsing.ValueToGridString(ARow.SchemaNode, DefNode.DefaultValue));
  end;
  Result := '';
end;

// Two captions can collapse onto the same identifier ('a/b' and 'a b'). The
// widget keys rows by name, so a clash would silently drop one of them.
function TSchemaPropertyGridController.UniqueGridKey(ARow: TGridPropertyMeta;
  const ACaption: string): string;
var
  Base  : string;
  Other : TGridPropertyMeta;
  N     : Integer;
  Taken : Boolean;
begin
  Base   := JsSafeKey(ACaption);
  Result := Base;
  N      := 1;
  repeat
    Taken := False;
    for Other in FRows do
      if (Other <> ARow) and SameText(Other.GridKey, Result) then
      begin
        Taken := True;
        Break;
      end;
    if Taken then
    begin
      Inc(N);
      Result := Base + '_' + IntToStr(N);
    end;
  until not Taken;
end;

procedure TSchemaPropertyGridController.AddGridProperty(ARow: TGridPropertyMeta);
var
  CaptionText : string;
begin
  CaptionText := ARow.DisplayName;
  if Assigned(ARow.SchemaNode) and ARow.SchemaNode.Required then
    CaptionText := CaptionText + ' *';
  if FShowTypeInLabel and Assigned(ARow.SchemaNode) then
    CaptionText := CaptionText + ' : ' + TSchemaTypeText.Describe(ARow.SchemaNode);
  ARow.GridLabel := CaptionText;
  ARow.GridKey   := UniqueGridKey(ARow, CaptionText);
  FGrid.AddProperty([ARow.GridKey, DisplayValueFor(ARow)]);
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
  Row.Path := FSchema.DiscriminatorProperty;
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
  Row.GridKey   := UniqueGridKey(Row, Row.GridLabel);
  FGrid.AddProperty([Row.GridKey, Current]);
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
    AddRowMeta(Key, Key, Key, EntrySchema, IsComplex, False);
    AddGridProperty(FRows.Last);
  end;
end;

procedure TSchemaPropertyGridController.AddPropertyRows(EffectiveSchema: TSchemaNode;
  const APathPrefix: string);
var
  Prop      : TSchemaProperty;
  PropNode  : TSchemaNode;
  IsComplex : Boolean;
  Path      : string;
  Title     : string;
begin
  if not Assigned(EffectiveSchema) then
    Exit;
  for Prop in EffectiveSchema.PropertyItems do
  begin
    if (APathPrefix = '') and (FSchema.DiscriminatorProperty <> '') and
      SameText(Prop.Name, FSchema.DiscriminatorProperty) then
      Continue;
    PropNode := TSchemaNode(Prop.Node);
    Path := TJsonPath.JoinPath(APathPrefix, Prop.Name);
    Title := DisplayTitle(PropNode, Prop.Name);
    if APathPrefix <> '' then
      Title := StringReplace(Path, '/', ' / ', [rfReplaceAll]);
    if ShouldFlatten(PropNode) then
    begin
      AddPropertyRows(PropNode, Path);
      Continue;
    end;
    if FShowOnlyPresent and (GetPropertyValue(Path) = nil) then
      Continue;
    IsComplex := TJsonValueParsing.IsComplexKind(PropNode);
    AddRowMeta(Path, Prop.Name, Title, PropNode, IsComplex, False);
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
    AddPropertyRows(Effective, '');
  TUniPropertyGridAccess(FGrid).PopulateGrid;
end;

function TSchemaPropertyGridController.GetPropertyValue(const APath: string): TJSONValue;
begin
  Result := nil;
  if not Assigned(FWorking) or (APath = '') then
    Exit;
  Result := TJsonPath.GetValue(FWorking, APath);
end;

procedure TSchemaPropertyGridController.SetPropertyValue(const APath: string;
  AValue: TJSONValue);
begin
  if not Assigned(FWorking) or (APath = '') then
  begin
    if Assigned(AValue) then
      AValue.Free;
    Exit;
  end;
  if not Assigned(AValue) then
  begin
    ClearPropertyValue(APath);
    Exit;
  end;
  TJsonPath.SetValue(FWorking, APath, AValue);
end;

procedure TSchemaPropertyGridController.ClearPropertyValue(const APath: string);
var
  Segments : IList<string>;
  Parent   : TJSONObject;
  Last     : string;
  I        : Integer;
  ParentPath: string;
begin
  if not Assigned(FWorking) or (APath = '') then
    Exit;
  Segments := TJsonPath.SplitPath(APath);
  if Segments.Count = 0 then
    Exit;
  Last := Segments[Segments.Count - 1];
  if Segments.Count = 1 then
    Parent := FWorking
  else
  begin
    ParentPath := '';
    for I := 0 to Segments.Count - 2 do
      ParentPath := TJsonPath.JoinPath(ParentPath, Segments[I]);
    Parent := TJsonPath.GetObject(FWorking, ParentPath);
  end;
  if Assigned(Parent) and Assigned(Parent.GetValue(Last)) then
    Parent.RemovePair(Last).Free;
end;

function TSchemaPropertyGridController.RowValue(ARow: TGridPropertyMeta): TJSONValue;
begin
  Result := nil;
  if Assigned(ARow) then
    Result := GetPropertyValue(ARow.Path);
end;

function TSchemaPropertyGridController.FindRowMeta(const PropName: string): TGridPropertyMeta;
var
  Row: TGridPropertyMeta;
begin
  Result := nil;
  for Row in FRows do
    if SameText(Row.GridKey, PropName) or SameText(Row.GridLabel, PropName)
      or SameText(Row.PropertyName, PropName) or SameText(Row.Path, PropName) then
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
    ClearPropertyValue(ARow.Path);
    Populate;
    Exit;
  end;
  Found := False;
  for Key in FSchema.DiscriminatorMapping.Keys do
    if SameText(Key, Trim(PropValue)) then
    begin
      Found := True;
      SetPropertyValue(ARow.Path, TJSONString.Create(Key));
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
    SetPropertyValue(ARow.Path, Parsed.Clone as TJSONValue);
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
  if FReadOnly then
  begin
    Handled := True;
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

procedure TSchemaPropertyGridController.ApplyComplexEdit(const APath: string;
  AValue: TJSONValue);
begin
  if Assigned(AValue) then
    SetPropertyValue(APath, AValue.Clone as TJSONValue)
  else if Assigned(FSchema) and FSchema.Nullable then
    SetPropertyValue(APath, TJSONNull.Create)
  else
    ClearPropertyValue(APath);
  Populate;
end;

function TSchemaPropertyGridController.ValidateAll(out ErrorMessage: string): Boolean;
var
  Row: TGridPropertyMeta;
  Val: TJSONValue;
begin
  for Row in FRows do
  begin
    if Row.Path = '' then
      Continue;
    Val := GetPropertyValue(Row.Path);
    if not TSchemaValidator.ValidateValue(Row.SchemaNode, Val, ErrorMessage) then
    begin
      ErrorMessage := Format('%s: %s', [Row.DisplayName, ErrorMessage]);
      Exit(False);
    end;
  end;
  Result := TSchemaValidator.ValidateObject(FSchema, FWorking, ErrorMessage);
end;

end.
