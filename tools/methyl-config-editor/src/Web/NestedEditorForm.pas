unit NestedEditorForm;

interface

uses
  System.Classes,
  System.JSON,
  System.UITypes,
  uniGUIForm,
  uniGUIApplication,
  uniGUITypes,
  uniPropertyGrid,
  uniButton,
  uniPanel,
  SchemaNode,
  SchemaPropertyGrid;

type
  TUniNestedEditorForm = class(TUniForm)
    PanelBottom: TUniPanel;
    btnOK: TUniButton;
    btnCancel: TUniButton;
    PropertyGrid: TUniPropertyGrid;
    procedure UniFormCreate(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
    procedure btnCancelClick(Sender: TObject);
    procedure PropertyGridPropertyChange(Sender: TObject; const PropName: string;
      var PropValue: string; var Handled: Boolean);
  private
    FController: TSchemaPropertyGridController;
    FSchema: TSchemaNode;
    FWorking: TJSONObject;
    FBreadcrumb: string;
    procedure OpenComplexEditor(Sender: TObject);
    procedure OpenNestedForRow(ARow: TGridPropertyMeta);
  public
    class function EditObject(const ABreadcrumb: string; ASchema: TSchemaNode;
      AObject: TJSONObject; out AEdited: TJSONObject): Boolean; static;
  end;

implementation

uses
  SchemaEditorService;

{$R *.dfm}

procedure TUniNestedEditorForm.UniFormCreate(Sender: TObject);
begin
  FController := TSchemaPropertyGridController.Create(PropertyGrid);
  FController.OnOpenComplex := OpenComplexEditor;
  PropertyGrid.OnPropertyChange := PropertyGridPropertyChange;
end;

procedure TUniNestedEditorForm.PropertyGridPropertyChange(Sender: TObject;
  const PropName: string; var PropValue: string; var Handled: Boolean);
begin
  FController.PropertyChange(Sender, PropName, PropValue, Handled);
end;

procedure TUniNestedEditorForm.OpenComplexEditor(Sender: TObject);
begin
  if Assigned(FController.PendingComplexRow) then
    OpenNestedForRow(FController.PendingComplexRow);
end;

procedure TUniNestedEditorForm.OpenNestedForRow(ARow: TGridPropertyMeta);
var
  Val: TJSONValue;
  Edited: TJSONValue;
  ChildTitle: string;
begin
  Val := FController.Working.GetValue(ARow.PropertyName);
  ChildTitle := FController.ChildBreadcrumb(ARow.DisplayName, FBreadcrumb);
  if TSchemaEditorService.EditValue(ChildTitle, ARow.SchemaNode, Val, Edited) then
  try
    FController.ApplyComplexEdit(ARow.PropertyName, Edited);
  finally
    Edited.Free;
  end;
end;

procedure TUniNestedEditorForm.btnCancelClick(Sender: TObject);
begin
  ModalResult := mrCancel;
end;

procedure TUniNestedEditorForm.btnOKClick(Sender: TObject);
var
  Err: string;
begin
  if not FController.ValidateAll(Err) then
  begin
    MessageDlg(Err, mtWarning, [mbOK]);
    Exit;
  end;
  ModalResult := mrOK;
end;

class function TUniNestedEditorForm.EditObject(const ABreadcrumb: string;
  ASchema: TSchemaNode; AObject: TJSONObject; out AEdited: TJSONObject): Boolean;
var
  Form: TUniNestedEditorForm;
begin
  Result := False;
  AEdited := nil;
  Form := TUniNestedEditorForm.Create(uniGUIApplication.UniApplication);
  try
    Form.FSchema := ASchema;
    Form.FWorking := AObject.Clone as TJSONObject;
    Form.FBreadcrumb := ABreadcrumb;
    if ABreadcrumb <> '' then
      Form.Caption := ABreadcrumb
    else if Assigned(ASchema) and (ASchema.Title <> '') then
      Form.Caption := ASchema.Title
    else
      Form.Caption := 'Property Editor';
    Form.FController.Bind(ASchema, Form.FWorking);
    Form.FController.Populate;
    Form.ShowModal;
    if Form.ModalResult = mrOK then
    begin
      AEdited := TJSONObject(Form.FWorking.Clone);
      Result := True;
    end;
  finally
    Form.Free;
  end;
end;

end.
