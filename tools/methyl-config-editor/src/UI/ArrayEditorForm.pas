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
    procedure RefreshList;
    function ItemSummary(Index: Integer): string;
    procedure EditItem(Index: Integer);
  public
    class function EditArray(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AArray: TJSONArray): Boolean;
  end;

implementation

uses
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
begin
  if (Index < 0) or (Index >= FWorking.Count) then
    Exit('');
  Val := FWorking.Items[Index];
  if Assigned(ItemSchema) then
    Result := Format('[%d] %s', [Index, TSchemaValueSummary.Describe(ItemSchema, Val)])
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
begin
  if Assigned(ItemSchema) then
    NewVal := TSchemaDefaults.CreateDefaultValue(ItemSchema)
  else
    NewVal := TJSONNull.Create;
  FWorking.AddElement(NewVal);
  RefreshList;
  ListBox.ItemIndex := FWorking.Count - 1;
  if Assigned(ItemSchema) and ItemSchema.IsComplex then
    EditItem(ListBox.ItemIndex);
end;

procedure TArrayEditorForm.btnRemoveClick(Sender: TObject);
var
  Idx: Integer;
begin
  Idx := ListBox.ItemIndex;
  if Idx < 0 then
    Exit;
  FWorking.Items[Idx].Free;
  FWorking.Remove(Idx);
  RefreshList;
end;

procedure TArrayEditorForm.EditItem(Index: Integer);
var
  Val: TJSONValue;
  Obj: TJSONObject;
  CloneObj: TJSONObject;
  ChildTitle: string;
begin
  if (Index < 0) or (Index >= FWorking.Count) then
    Exit;
  Val := FWorking.Items[Index];
  if not Assigned(ItemSchema) then
    Exit;
  ChildTitle := FBreadcrumb + Format(' [%d]', [Index]);
  if ItemSchema.Kind = skObject then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
    begin
      Obj := TSchemaDefaults.CreateDefaultObject(ItemSchema);
      FWorking.Items[Index].Free;
      FWorking.Items[Index] := Obj;
    end;
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TPropertyEditorForm.EditObject(Self, ChildTitle, ItemSchema, CloneObj) then
      begin
        FWorking.Items[Index].Free;
        FWorking.Items[Index] := CloneObj.Clone as TJSONObject;
      end;
    finally
      CloneObj.Free;
    end;
    RefreshList;
    ListBox.ItemIndex := Index;
  end;
end;

procedure TArrayEditorForm.btnEditClick(Sender: TObject);
begin
  EditItem(ListBox.ItemIndex);
end;

procedure TArrayEditorForm.btnUpClick(Sender: TObject);
var
  Idx: Integer;
  Val: TJSONValue;
begin
  Idx := ListBox.ItemIndex;
  if Idx <= 0 then
    Exit;
  Val := FWorking.Items[Idx];
  FWorking.Remove(Idx);
  FWorking.Insert(Idx - 1, Val);
  RefreshList;
  ListBox.ItemIndex := Idx - 1;
end;

procedure TArrayEditorForm.btnDownClick(Sender: TObject);
var
  Idx: Integer;
  Val: TJSONValue;
begin
  Idx := ListBox.ItemIndex;
  if (Idx < 0) or (Idx >= FWorking.Count - 1) then
    Exit;
  Val := FWorking.Items[Idx];
  FWorking.Remove(Idx);
  FWorking.Insert(Idx + 1, Val);
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
      while AArray.Count > 0 do
      begin
        AArray.Items[0].Free;
        AArray.Remove(0);
      end;
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
