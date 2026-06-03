unit DictEditorForm;

interface

uses
  Winapi.Windows,
  Winapi.Messages,
  System.SysUtils,
  System.Classes,
  System.Generics.Collections,
  Vcl.Graphics,
  Vcl.Controls,
  Vcl.Forms,
  Vcl.Dialogs,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  Vcl.Grids,
  System.JSON,
  SchemaNode,
  SchemaDefaults,
  SchemaValueSummary;

type
  TDictEditorForm = class(TForm)
    PanelBottom: TPanel;
    btnOK: TButton;
    btnCancel: TButton;
    PanelButtons: TPanel;
    btnAdd: TButton;
    btnRemove: TButton;
    btnEdit: TButton;
    StringGrid: TStringGrid;
    procedure FormCreate(Sender: TObject);
    procedure FormDestroy(Sender: TObject);
    procedure btnAddClick(Sender: TObject);
    procedure btnRemoveClick(Sender: TObject);
    procedure btnEditClick(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
  private
    FSchema: TSchemaNode;
    FObject: TJSONObject;
    FWorking: TJSONObject;
    FBreadcrumb: string;
    FValueSchemaFallback: TSchemaNode;
    function ValueSchema: TSchemaNode;
    function EditWrappedValue(const ATitle: string; ASchema: TSchemaNode;
      AValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
    function IsRegistryResolutionRequired(ASchema: TSchemaNode): Boolean;
    procedure ShowMissingSchema(const Key: string);
    procedure SetWorkingValue(const Key: string; AValue: TJSONValue);
    function TryResolveValueSchema(const Key: string; out ASchema: TSchemaNode): Boolean;
    procedure SetupGrid;
    procedure LoadGrid;
    function SaveGrid(ARequireSchemas: Boolean = True): Boolean;
    function SelectedRow: Integer;
  public
    class function EditDictionary(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
  end;

implementation

uses
  System.UITypes,
  ArrayEditorForm,
  PropertyEditorForm,
  SchemaCatalog;

{$R *.dfm}

procedure TDictEditorForm.FormDestroy(Sender: TObject);
begin
  FValueSchemaFallback.Free;
  if Assigned(FWorking) then
    FWorking.Free;
end;

procedure TDictEditorForm.FormCreate(Sender: TObject);
begin
  SetupGrid;
end;

function TDictEditorForm.ValueSchema: TSchemaNode;
begin
  if Assigned(FSchema.AdditionalPropertiesSchema) then
    Exit(FSchema.AdditionalPropertiesSchema);
  if not Assigned(FValueSchemaFallback) then
  begin
    FValueSchemaFallback := TSchemaNode.Create;
    FValueSchemaFallback.Kind := skString;
  end;
  Result := FValueSchemaFallback;
end;

function TDictEditorForm.IsRegistryResolutionRequired(ASchema: TSchemaNode): Boolean;
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

procedure TDictEditorForm.ShowMissingSchema(const Key: string);
begin
  MessageDlg(Format(
    'No registered schema was found for "%s". Add a matching *.schema.json file to the schema folder before editing this value.',
    [Key]), TMsgDlgType.mtInformation, [TMsgDlgBtn.mbOK], 0);
end;

function TDictEditorForm.TryResolveValueSchema(const Key: string;
  out ASchema: TSchemaNode): Boolean;
var
  Catalog: TSchemaCatalog;
begin
  ASchema := ValueSchema;
  if not IsRegistryResolutionRequired(ASchema) then
    Exit(Assigned(ASchema));

  ASchema := nil;
  Catalog := TSchemaCatalog.Current;
  Result := Assigned(Catalog) and Catalog.TryResolveSchema(Key, ASchema) and
    Assigned(ASchema);
end;

procedure TDictEditorForm.SetupGrid;
begin
  StringGrid.Cells[0, 0] := 'Key';
  StringGrid.Cells[1, 0] := 'Value';
  StringGrid.FixedRows := 1;
end;

procedure TDictEditorForm.LoadGrid;
var
  I: Integer;
  Pair: TJSONPair;
  ItemSchema: TSchemaNode;
begin
  StringGrid.RowCount := FWorking.Count + 1;
  if StringGrid.RowCount < 2 then
    StringGrid.RowCount := 2;
  I := 1;
  for Pair in FWorking do
  begin
    StringGrid.Cells[0, I] := Pair.JsonString.Value;
    if TryResolveValueSchema(Pair.JsonString.Value, ItemSchema) then
      StringGrid.Cells[1, I] := TSchemaValueSummary.Describe(ItemSchema, Pair.JsonValue)
    else
      StringGrid.Cells[1, I] := '(no registered schema)';
    Inc(I);
  end;
end;

function TDictEditorForm.SaveGrid(ARequireSchemas: Boolean): Boolean;
var
  R: Integer;
  Key: string;
  Existing: TJSONValue;
  NewObj: TJSONObject;
  ItemSchema: TSchemaNode;
begin
  Result := False;
  NewObj := TJSONObject.Create;
  try
    for R := 1 to StringGrid.RowCount - 1 do
    begin
      Key := Trim(StringGrid.Cells[0, R]);
      if Key = '' then
        Continue;
      if not TryResolveValueSchema(Key, ItemSchema) then
        if ARequireSchemas then
        begin
          ShowMissingSchema(Key);
          Exit;
        end
        else
          ItemSchema := nil;
      Existing := FWorking.GetValue(Key);
      if Assigned(Existing) then
        NewObj.AddPair(Key, Existing.Clone as TJSONValue)
      else if Assigned(ItemSchema) then
        NewObj.AddPair(Key, TSchemaDefaults.CreateDefaultValue(ItemSchema))
      else
        NewObj.AddPair(Key, TJSONNull.Create);
    end;
    while FWorking.Count > 0 do
      FWorking.RemovePair(FWorking.Pairs[0].JsonString.Value).Free;
    for var Pair in NewObj do
      FWorking.AddPair(Pair.JsonString.Value, Pair.JsonValue.Clone as TJSONValue);
    Result := True;
  finally
    NewObj.Free;
  end;
end;

procedure TDictEditorForm.SetWorkingValue(const Key: string; AValue: TJSONValue);
var
  Existing: TJSONPair;
begin
  Existing := FWorking.RemovePair(Key);
  if Assigned(Existing) then
    Existing.Free;
  FWorking.AddPair(Key, AValue);
end;

function TDictEditorForm.SelectedRow: Integer;
begin
  Result := StringGrid.Row;
  if Result < 1 then
    Result := -1;
end;

procedure TDictEditorForm.btnAddClick(Sender: TObject);
begin
  if StringGrid.RowCount = 1 then
    StringGrid.RowCount := 2
  else
    StringGrid.RowCount := StringGrid.RowCount + 1;
  StringGrid.Row := StringGrid.RowCount - 1;
  StringGrid.Cells[0, StringGrid.Row] := '';
  StringGrid.Cells[1, StringGrid.Row] := TSchemaValueSummary.Describe(ValueSchema, nil);
end;

procedure TDictEditorForm.btnRemoveClick(Sender: TObject);
var
  R, I, C: Integer;
begin
  R := SelectedRow;
  if R < 0 then
    Exit;
  if StringGrid.RowCount <= 2 then
  begin
    StringGrid.Cells[0, 1] := '';
    StringGrid.Cells[1, 1] := '';
  end
  else
  begin
    for I := R to StringGrid.RowCount - 2 do
      for C := 0 to StringGrid.ColCount - 1 do
        StringGrid.Cells[C, I] := StringGrid.Cells[C, I + 1];
    StringGrid.RowCount := StringGrid.RowCount - 1;
  end;
end;

procedure TDictEditorForm.btnEditClick(Sender: TObject);
var
  R: Integer;
  Key: string;
  Val: TJSONValue;
  Obj: TJSONObject;
  CloneObj: TJSONObject;
  Arr: TJSONArray;
  CloneArr: TJSONArray;
  ChildTitle: string;
  VS: TSchemaNode;
  Edited: TJSONValue;
begin
  if not SaveGrid(False) then
    Exit;
  R := SelectedRow;
  if R < 0 then
    Exit;
  Key := Trim(StringGrid.Cells[0, R]);
  if Key = '' then
    Exit;
  if not TryResolveValueSchema(Key, VS) then
  begin
    ShowMissingSchema(Key);
    Exit;
  end;
  Val := FWorking.GetValue(Key);
  if FBreadcrumb = '' then
    ChildTitle := Key
  else
    ChildTitle := FBreadcrumb + ' / ' + Key;
  if Assigned(VS) and (VS.Kind = skObject) then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
      Obj := TSchemaDefaults.CreateDefaultObject(VS);
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TPropertyEditorForm.EditObject(Self, ChildTitle, VS, CloneObj) then
        SetWorkingValue(Key, CloneObj.Clone as TJSONObject);
    finally
      CloneObj.Free;
      if Obj <> Val then
        Obj.Free;
    end;
  end
  else if Assigned(VS) and (VS.Kind = skDictionary) then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
      Obj := TJSONObject.Create;
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TDictEditorForm.EditDictionary(Self, ChildTitle, VS, CloneObj) then
        SetWorkingValue(Key, CloneObj.Clone as TJSONObject);
    finally
      CloneObj.Free;
      if Obj <> Val then
        Obj.Free;
    end;
  end
  else if Assigned(VS) and (VS.Kind = skArray) then
  begin
    if Val is TJSONArray then
      Arr := TJSONArray(Val)
    else
      Arr := TJSONArray.Create;
    CloneArr := Arr.Clone as TJSONArray;
    try
      if TArrayEditorForm.EditArray(Self, ChildTitle, VS, CloneArr) then
        SetWorkingValue(Key, CloneArr.Clone as TJSONArray);
    finally
      CloneArr.Free;
      if Arr <> Val then
        Arr.Free;
    end;
  end
  else if Assigned(VS) and (VS.Kind <> skUnknown) then
  begin
    if EditWrappedValue(ChildTitle, VS, Val, Edited) then
      SetWorkingValue(Key, Edited);
  end;
  LoadGrid;
  StringGrid.Row := R;
end;

function TDictEditorForm.EditWrappedValue(const ATitle: string; ASchema: TSchemaNode;
  AValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
var
  WrapperSchema: TSchemaNode;
  WrapperObject: TJSONObject;
  Edited: TJSONValue;
begin
  Result := False;
  AEditedValue := nil;
  WrapperSchema := TSchemaNode.Create;
  WrapperObject := TJSONObject.Create;
  try
    WrapperSchema.Kind := skObject;
    WrapperSchema.Title := ATitle;
    WrapperSchema.AddProperty('value', ASchema);
    if Assigned(AValue) then
      WrapperObject.AddPair('value', AValue.Clone as TJSONValue)
    else
      WrapperObject.AddPair('value', TSchemaDefaults.CreateDefaultValue(ASchema));
    if TPropertyEditorForm.EditObject(Self, ATitle, WrapperSchema, WrapperObject) then
    begin
      Edited := WrapperObject.GetValue('value');
      if Assigned(Edited) then
        AEditedValue := Edited.Clone as TJSONValue
      else
        AEditedValue := TJSONNull.Create;
      Result := True;
    end;
  finally
    WrapperObject.Free;
    WrapperSchema.Free;
  end;
end;

procedure TDictEditorForm.btnOKClick(Sender: TObject);
begin
  if not SaveGrid then
    Exit;
  ModalResult := mrOk;
end;

class function TDictEditorForm.EditDictionary(AOwner: TComponent;
  const ABreadcrumb: string; ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
var
  Form: TDictEditorForm;
  Pair: TJSONPair;
begin
  Form := TDictEditorForm.Create(AOwner);
  try
    Form.FSchema := ASchema;
    Form.FObject := AObject;
    Form.FWorking := AObject.Clone as TJSONObject;
    Form.FBreadcrumb := ABreadcrumb;
    Form.Caption := ABreadcrumb;
    Form.LoadGrid;
    if Form.ShowModal = mrOk then
    begin
      while AObject.Count > 0 do
        AObject.RemovePair(AObject.Pairs[0].JsonString.Value).Free;
      for Pair in Form.FWorking do
        AObject.AddPair(Pair.JsonString.Value, Pair.JsonValue.Clone as TJSONValue);
      Result := True;
    end
    else
      Result := False;
  finally
    Form.Free;
  end;
end;

end.
