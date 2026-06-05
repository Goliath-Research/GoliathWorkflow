unit WebArrayEditorForm;

interface

uses
  System.Classes,
  System.JSON,
  System.SysUtils,
  System.UITypes,
  uniGUIForm,
  uniGUIApplication,
  uniGUITypes,
  uniButton,
  uniPanel,
  uniListBox,
  SchemaNode, uniGUIClasses, uniMultiItem, Vcl.Controls, Vcl.Forms,
  uniGUIBaseClasses;

type
  TUniWebArrayEditorForm = class(TUniForm)
    PanelBottom: TUniPanel;
    btnOK: TUniButton;
    btnCancel: TUniButton;
    PanelButtons: TUniPanel;
    btnAdd: TUniButton;
    btnRemove: TUniButton;
    btnEdit: TUniButton;
    btnUp: TUniButton;
    btnDown: TUniButton;
    ListBox: TUniListBox;
    procedure btnAddClick(Sender: TObject);
    procedure btnRemoveClick(Sender: TObject);
    procedure btnEditClick(Sender: TObject);
    procedure btnUpClick(Sender: TObject);
    procedure btnDownClick(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
    procedure btnCancelClick(Sender: TObject);
  private
    FSchema: TSchemaNode;
    FWorking: TJSONArray;
    FBreadcrumb: string;
    function ItemSchema: TSchemaNode;
    function ItemSummary(Index: Integer): string;
    procedure RefreshList;
    procedure EditItem(Index: Integer);
    function EditWrappedValue(const ATitle: string; ASchema: TSchemaNode;
      AValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
  public
    class function EditArray(const ABreadcrumb: string; ASchema: TSchemaNode;
      AArray: TJSONArray; out AEdited: TJSONArray): Boolean; static;
  end;

implementation

uses
  JsonArrayOps,
  SchemaDefaults,
  SchemaValueSummary,
  NestedEditorForm,
  SchemaEditorService;

{$R *.dfm}

function TUniWebArrayEditorForm.ItemSchema: TSchemaNode;
begin
  Result := FSchema.ItemsSchema;
end;

function TUniWebArrayEditorForm.ItemSummary(Index: Integer): string;
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

procedure TUniWebArrayEditorForm.RefreshList;
var
  I: Integer;
begin
  ListBox.Items.Clear;
  for I := 0 to FWorking.Count - 1 do
    ListBox.Items.Add(ItemSummary(I));
end;

function TUniWebArrayEditorForm.EditWrappedValue(const ATitle: string;
  ASchema: TSchemaNode; AValue: TJSONValue; out AEditedValue: TJSONValue): Boolean;
begin
  Result := TSchemaEditorService.EditValue(ATitle, ASchema, AValue, AEditedValue);
end;

procedure TUniWebArrayEditorForm.EditItem(Index: Integer);
var
  Val: TJSONValue;
  Obj: TJSONObject;
  CloneObj: TJSONObject;
  Arr: TJSONArray;
  CloneArr: TJSONArray;
  ChildTitle: string;
  Schema: TSchemaNode;
  Edited: TJSONValue;
  EditedObj: TJSONObject;
  EditedArr: TJSONArray;
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
    EditedObj := nil;
    try
      if TUniNestedEditorForm.EditObject(ChildTitle, Schema, CloneObj, EditedObj) then
      begin
        TJsonArrayOps.ReplaceElement(FWorking, Index, EditedObj);
        EditedObj := nil;
      end;
    finally
      EditedObj.Free;
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
    EditedObj := nil;
    try
      if TUniNestedEditorForm.EditObject(ChildTitle, Schema, CloneObj, EditedObj) then
      begin
        TJsonArrayOps.ReplaceElement(FWorking, Index, EditedObj);
        EditedObj := nil;
      end;
    finally
      EditedObj.Free;
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
    EditedArr := nil;
    try
      if TUniWebArrayEditorForm.EditArray(ChildTitle, Schema, CloneArr, EditedArr) then
      begin
        TJsonArrayOps.ReplaceElement(FWorking, Index, EditedArr);
        EditedArr := nil;
      end;
    finally
      EditedArr.Free;
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
    [ChildTitle]), mtInformation, [mbOK]);
  RefreshList;
  ListBox.ItemIndex := Index;
end;

procedure TUniWebArrayEditorForm.btnAddClick(Sender: TObject);
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

procedure TUniWebArrayEditorForm.btnRemoveClick(Sender: TObject);
var
  Idx: Integer;
begin
  Idx := ListBox.ItemIndex;
  if Idx < 0 then
    Exit;
  TJsonArrayOps.RemoveElement(FWorking, Idx);
  RefreshList;
end;

procedure TUniWebArrayEditorForm.btnEditClick(Sender: TObject);
begin
  EditItem(ListBox.ItemIndex);
end;

procedure TUniWebArrayEditorForm.btnUpClick(Sender: TObject);
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

procedure TUniWebArrayEditorForm.btnDownClick(Sender: TObject);
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

procedure TUniWebArrayEditorForm.btnCancelClick(Sender: TObject);
begin
  ModalResult := mrCancel;
end;

procedure TUniWebArrayEditorForm.btnOKClick(Sender: TObject);
begin
  ModalResult := mrOK;
end;

class function TUniWebArrayEditorForm.EditArray(const ABreadcrumb: string;
  ASchema: TSchemaNode; AArray: TJSONArray; out AEdited: TJSONArray): Boolean;
var
  Form: TUniWebArrayEditorForm;
begin
  Result := False;
  AEdited := nil;
  Form := TUniWebArrayEditorForm.Create(uniGUIApplication.UniApplication);
  try
    Form.FSchema := ASchema;
    Form.FWorking := AArray.Clone as TJSONArray;
    Form.FBreadcrumb := ABreadcrumb;
    Form.Caption := ABreadcrumb;
    Form.RefreshList;
    Form.ShowModal;
    if Form.ModalResult = mrOK then
    begin
      AEdited := Form.FWorking.Clone as TJSONArray;
      Result := True;
    end;
  finally
    Form.Free;
  end;
end;

end.
