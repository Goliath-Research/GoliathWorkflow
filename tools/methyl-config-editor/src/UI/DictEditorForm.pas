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
    procedure SetupGrid;
    procedure LoadGrid;
    procedure SaveGrid;
    function SelectedRow: Integer;
  public
    class function EditDictionary(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
  end;

implementation

uses
  PropertyEditorForm,
  TypedStepSchemas;

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
begin
  StringGrid.RowCount := FWorking.Count + 1;
  if StringGrid.RowCount < 2 then
    StringGrid.RowCount := 2;
  I := 1;
  for Pair in FWorking do
  begin
    StringGrid.Cells[0, I] := Pair.JsonString.Value;
    StringGrid.Cells[1, I] := TSchemaValueSummary.Describe(ValueSchema, Pair.JsonValue);
    Inc(I);
  end;
end;

procedure TDictEditorForm.SaveGrid;
var
  R: Integer;
  Key, Summary: string;
  Existing: TJSONValue;
  NewObj: TJSONObject;
begin
  NewObj := TJSONObject.Create;
  for R := 1 to StringGrid.RowCount - 1 do
  begin
    Key := Trim(StringGrid.Cells[0, R]);
    if Key = '' then
      Continue;
    Summary := StringGrid.Cells[1, R];
    Existing := FWorking.GetValue(Key);
    if Assigned(Existing) then
      NewObj.AddPair(Key, Existing.Clone as TJSONValue)
    else
      NewObj.AddPair(Key, TSchemaDefaults.CreateDefaultValue(ValueSchema));
  end;
  while FWorking.Count > 0 do
    FWorking.RemovePair(FWorking.Pairs[0].JsonString.Value).Free;
  for var Pair in NewObj do
    FWorking.AddPair(Pair.JsonString.Value, Pair.JsonValue.Clone as TJSONValue);
  NewObj.Free;
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
  ChildTitle: string;
  VS: TSchemaNode;
  TypedRoot: TSchemaNode;
begin
  SaveGrid;
  R := SelectedRow;
  if R < 0 then
    Exit;
  Key := Trim(StringGrid.Cells[0, R]);
  if Key = '' then
    Exit;
  VS := ValueSchema;
  if TTypedStepSchemas.TryLoadStepRoot(Key, TypedRoot) then
    VS := TypedRoot;
  Val := FWorking.GetValue(Key);
  ChildTitle := FBreadcrumb + ' › ' + Key;
  if VS.Kind = skObject then
  begin
    if Val is TJSONObject then
      Obj := TJSONObject(Val)
    else
    begin
      Obj := TSchemaDefaults.CreateDefaultObject(VS);
      FWorking.RemovePair(Key).Free;
      FWorking.AddPair(Key, Obj);
    end;
    CloneObj := Obj.Clone as TJSONObject;
    try
      if TPropertyEditorForm.EditObject(Self, ChildTitle, VS, CloneObj) then
      begin
        FWorking.RemovePair(Key).Free;
        FWorking.AddPair(Key, CloneObj.Clone as TJSONObject);
      end;
    finally
      CloneObj.Free;
    end;
    LoadGrid;
    StringGrid.Row := R;
  end;
end;

procedure TDictEditorForm.btnOKClick(Sender: TObject);
begin
  SaveGrid;
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
