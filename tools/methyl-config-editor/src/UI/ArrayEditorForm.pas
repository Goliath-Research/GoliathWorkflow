unit ArrayEditorForm;

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

procedure ClearArray(AArray: TJSONArray);
var
  Removed: TJSONValue;
begin
  while AArray.Count > 0 do
  begin
    Removed := AArray.Remove(0);
    Removed.Free;
  end;
end;

procedure ReplaceArrayElement(AArray: TJSONArray; Index: Integer; AValue: TJSONValue);
var
  I: Integer;
  Tail: TObjectList<TJSONValue>;
  Removed: TJSONValue;
begin
  Tail := TObjectList<TJSONValue>.Create(True);
  try
    for I := Index + 1 to AArray.Count - 1 do
      Tail.Add(AArray.Items[I].Clone as TJSONValue);
    while AArray.Count > Index do
    begin
      Removed := AArray.Remove(AArray.Count - 1);
      Removed.Free;
    end;
    AArray.AddElement(AValue);
    while Tail.Count > 0 do
      AArray.AddElement(Tail.Extract(Tail[0]));
  finally
    Tail.Free;
  end;
end;

procedure RemoveArrayElement(AArray: TJSONArray; Index: Integer);
var
  I: Integer;
  Values: TObjectList<TJSONValue>;
begin
  Values := TObjectList<TJSONValue>.Create(True);
  try
    for I := 0 to AArray.Count - 1 do
      if I <> Index then
        Values.Add(AArray.Items[I].Clone as TJSONValue);
    ClearArray(AArray);
    while Values.Count > 0 do
      AArray.AddElement(Values.Extract(Values[0]));
  finally
    Values.Free;
  end;
end;

procedure MoveArrayElement(AArray: TJSONArray; FromIndex, ToIndex: Integer);
var
  I: Integer;
  Values: TObjectList<TJSONValue>;
  Moving: TJSONValue;
begin
  Values := TObjectList<TJSONValue>.Create(True);
  try
    for I := 0 to AArray.Count - 1 do
      Values.Add(AArray.Items[I].Clone as TJSONValue);
    Moving := Values.Extract(Values[FromIndex]);
    Values.Insert(ToIndex, Moving);
    ClearArray(AArray);
    while Values.Count > 0 do
      AArray.AddElement(Values.Extract(Values[0]));
  finally
    Values.Free;
  end;
end;

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
  if Assigned(Schema) and Schema.IsComplex then
    EditItem(ListBox.ItemIndex);
end;

procedure TArrayEditorForm.btnRemoveClick(Sender: TObject);
var
  Idx: Integer;
begin
  Idx := ListBox.ItemIndex;
  if Idx < 0 then
    Exit;
  RemoveArrayElement(FWorking, Idx);
  RefreshList;
end;

procedure TArrayEditorForm.EditItem(Index: Integer);
var
  Val: TJSONValue;
  Obj: TJSONObject;
  CloneObj: TJSONObject;
  ChildTitle: string;
  Schema: TSchemaNode;
begin
  if (Index < 0) or (Index >= FWorking.Count) then
    Exit;
  Val := FWorking.Items[Index];
  Schema := ItemSchema;
  if not Assigned(Schema) then
    Exit;
  ChildTitle := FBreadcrumb + Format(' [%d]', [Index]);
  if Schema.Kind = skObject then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
    begin
      Obj := TSchemaDefaults.CreateDefaultObject(Schema);
      ReplaceArrayElement(FWorking, Index, Obj);
    end;
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TPropertyEditorForm.EditObject(Self, ChildTitle, Schema, CloneObj) then
        ReplaceArrayElement(FWorking, Index, CloneObj.Clone as TJSONObject);
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
begin
  Idx := ListBox.ItemIndex;
  if Idx <= 0 then
    Exit;
  MoveArrayElement(FWorking, Idx, Idx - 1);
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
  MoveArrayElement(FWorking, Idx, Idx + 1);
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
      ClearArray(AArray);
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
