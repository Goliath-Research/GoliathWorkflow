unit ArrayEditorForm;

interface

uses
  Winapi.Windows,
  Winapi.Messages,
  System.SysUtils,
  System.Classes,
  Vcl.Graphics,
  Vcl.Controls,
  Vcl.Forms,
  Vcl.Dialogs,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  System.JSON,
  SchemaNode,
  SchemaDefaults,
  SchemaValueSummary;

type
  TArrayEditorForm = class(TForm)
    PanelBottom: TPanel;
    btnOK: TButton;
    btnCancel: TButton;
    PanelButtons: TPanel;
    btnAdd: TButton;
    btnRemove: TButton;
    btnEdit: TButton;
    btnUp: TButton;
    btnDown: TButton;
    ListBox: TListBox;
    procedure FormDestroy(Sender: TObject);
    procedure btnAddClick(Sender: TObject);
    procedure btnRemoveClick(Sender: TObject);
    procedure btnEditClick(Sender: TObject);
    procedure btnUpClick(Sender: TObject);
    procedure btnDownClick(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
  private
    FSchema: TSchemaNode;
    FArray: TJSONArray;
    FWorking: TJSONArray;
    FBreadcrumb: string;
    function ItemSchema: TSchemaNode;
    function EditWrappedValue(const ATitle: string; ASchema: TSchemaNode;
      AValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
    procedure RefreshList;
    function ItemSummary(Index: Integer): string;
    procedure EditItem(Index: Integer);
  public
    class function EditArray(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AArray: TJSONArray): Boolean;
  end;

implementation

uses
  System.UITypes,
  JsonArrayOps,
  PropertyEditorForm;

{$R *.dfm}

procedure TArrayEditorForm.FormDestroy(Sender: TObject);
begin
  if Assigned(FWorking) then
    FWorking.Free;
end;

function TArrayEditorForm.ItemSchema: TSchemaNode;
begin
  Result := FSchema.ItemsSchema;
end;

function TArrayEditorForm.ItemSummary(Index: Integer): string;
var
  Val: TJSONValue;
  Schema: TSchemaNode;
begin
  if (Index < 0) or (Index >= FWorking.Count) then
    Exit('');
  Val := FWorking.Items[Index];
  Schema := ItemSchema;
  if Assigned(Schema) then
    Result := Format('[%d] %s', [Index, TSchemaValueSummary.Describe(Schema, Val)])
  else
    Result := Format('[%d] %s', [Index, Val.Value]);
end;

procedure TArrayEditorForm.RefreshList;
var
  I: Integer;
begin
  ListBox.Items.Clear;
  for I := 0 to FWorking.Count - 1 do
    ListBox.Items.Add(ItemSummary(I));
end;

procedure TArrayEditorForm.btnAddClick(Sender: TObject);
var
  NewVal: TJSONValue;
  Schema: TSchemaNode;
begin
  Schema := ItemSchema;
  if Assigned(Schema) then
    NewVal := TSchemaDefaults.CreateDefaultValue(Schema)
  else
    NewVal := TJSONNull.Create;
  FWorking.AddElement(NewVal);
  RefreshList;
  ListBox.ItemIndex := FWorking.Count - 1;
  EditItem(ListBox.ItemIndex);
end;

procedure TArrayEditorForm.btnRemoveClick(Sender: TObject);
var
  Idx: Integer;
begin
  Idx := ListBox.ItemIndex;
  if Idx < 0 then
    Exit;
  TJsonArrayOps.RemoveElement(FWorking, Idx);
  RefreshList;
end;

procedure TArrayEditorForm.EditItem(Index: Integer);
var
  Val: TJSONValue;
  Obj: TJSONObject;
  CloneObj: TJSONObject;
  Arr: TJSONArray;
  CloneArr: TJSONArray;
  ChildTitle: string;
  Schema: TSchemaNode;
  Edited: TJSONValue;
begin
  if (Index < 0) or (Index >= FWorking.Count) then
    Exit;
  Val := FWorking.Items[Index];
  Schema := ItemSchema;
  if FBreadcrumb = '' then
    ChildTitle := Format('[%d]', [Index])
  else
    ChildTitle := FBreadcrumb + Format(' / [%d]', [Index]);
  if Assigned(Schema) and (Schema.Kind = skObject) then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
    begin
      Obj := TSchemaDefaults.CreateDefaultObject(Schema);
      TJsonArrayOps.ReplaceElement(FWorking, Index, Obj);
    end;
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TPropertyEditorForm.EditObject(Self, ChildTitle, Schema, CloneObj) then
        TJsonArrayOps.ReplaceElement(FWorking, Index, CloneObj.Clone as TJSONObject);
    finally
      CloneObj.Free;
    end;
    RefreshList;
    ListBox.ItemIndex := Index;
    Exit;
  end;
  if Assigned(Schema) and (Schema.Kind = skDictionary) then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
      Obj := TJSONObject.Create;
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TPropertyEditorForm.EditObject(Self, ChildTitle, Schema, CloneObj) then
        TJsonArrayOps.ReplaceElement(FWorking, Index, CloneObj.Clone as TJSONObject);
    finally
      CloneObj.Free;
      if Obj <> Val then
        Obj.Free;
    end;
    RefreshList;
    ListBox.ItemIndex := Index;
    Exit;
  end;
  if Assigned(Schema) and (Schema.Kind = skArray) then
  begin
    if Val is TJSONArray then
      Arr := TJSONArray(Val)
    else
      Arr := TJSONArray.Create;
    CloneArr := Arr.Clone as TJSONArray;
    try
      if TArrayEditorForm.EditArray(Self, ChildTitle, Schema, CloneArr) then
        TJsonArrayOps.ReplaceElement(FWorking, Index, CloneArr.Clone as TJSONArray);
    finally
      CloneArr.Free;
      if Arr <> Val then
        Arr.Free;
    end;
    RefreshList;
    ListBox.ItemIndex := Index;
    Exit;
  end;
  if Assigned(Schema) and (Schema.Kind <> skUnknown) then
  begin
    if EditWrappedValue(ChildTitle, Schema, Val, Edited) then
      TJsonArrayOps.ReplaceElement(FWorking, Index, Edited);
    RefreshList;
    ListBox.ItemIndex := Index;
    Exit;
  end;
  MessageDlg(Format(
    'No schema is available for "%s". Array items require an item schema before they can be edited.',
    [ChildTitle]), TMsgDlgType.mtInformation, [TMsgDlgBtn.mbOK], 0);
  RefreshList;
  ListBox.ItemIndex := Index;
end;

function TArrayEditorForm.EditWrappedValue(const ATitle: string; ASchema: TSchemaNode;
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

procedure TArrayEditorForm.btnEditClick(Sender: TObject);
begin
  EditItem(ListBox.ItemIndex);
end;

procedure TArrayEditorForm.btnUpClick(Sender: TObject);
var
  Idx: Integer;
begin
  Idx := ListBox.ItemIndex;
  if Idx <= 0 then
    Exit;
  TJsonArrayOps.MoveElement(FWorking, Idx, Idx - 1);
  RefreshList;
  ListBox.ItemIndex := Idx - 1;
end;

procedure TArrayEditorForm.btnDownClick(Sender: TObject);
var
  Idx: Integer;
begin
  Idx := ListBox.ItemIndex;
  if (Idx < 0) or (Idx >= FWorking.Count - 1) then
    Exit;
  TJsonArrayOps.MoveElement(FWorking, Idx, Idx + 1);
  RefreshList;
  ListBox.ItemIndex := Idx + 1;
end;

procedure TArrayEditorForm.btnOKClick(Sender: TObject);
begin
  ModalResult := mrOk;
end;

class function TArrayEditorForm.EditArray(AOwner: TComponent; const ABreadcrumb: string;
  ASchema: TSchemaNode; AArray: TJSONArray): Boolean;
var
  Form: TArrayEditorForm;
  I: Integer;
begin
  Form := TArrayEditorForm.Create(AOwner);
  try
    Form.FSchema := ASchema;
    Form.FArray := AArray;
    Form.FWorking := AArray.Clone as TJSONArray;
    Form.FBreadcrumb := ABreadcrumb;
    Form.Caption := ABreadcrumb;
    Form.RefreshList;
    if Form.ShowModal = mrOk then
    begin
      TJsonArrayOps.Clear(AArray);
      for I := 0 to Form.FWorking.Count - 1 do
        AArray.AddElement(Form.FWorking.Items[I].Clone as TJSONValue);
      Result := True;
    end
    else
      Result := False;
  finally
    Form.Free;
  end;
end;

end.
