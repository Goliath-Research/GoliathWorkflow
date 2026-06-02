unit PropertyEditorForm;

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
  SchemaBranchResolver,
  SchemaDefaults,
  SchemaValidator,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorRegistry,
  SchemaEditorKeys;

type
  TPropertyEditorForm = class(TForm)
    PanelBottom: TPanel;
    btnOK: TButton;
    btnCancel: TButton;
    ScrollBox: TScrollBox;
    procedure FormCreate(Sender: TObject);
    procedure FormDestroy(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
    procedure btnCancelClick(Sender: TObject);
  private
    FSchema: TSchemaNode;
    FObject: TJSONObject;
    FWorking: TJSONObject;
    FBreadcrumb: string;
    FContext: IPropertyEditorContext;
    FRows: TObjectList<TPropertyRow>;
    procedure ClearRows;
    procedure BuildRows;
    procedure BuildPropertyRows(EffectiveSchema: TSchemaNode);
    procedure BuildDiscriminatorRow;
    function CreateRowPanel(const PropTitle: string; Required: Boolean): TPropertyRow;
    function GetPropertyValue(const PropName: string): TJSONValue;
    procedure SetPropertyValue(const PropName: string; AValue: TJSONValue);
    function ValidateAll(out ErrorMessage: string): Boolean;
  public
    class function EditObject(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
  end;

implementation

uses
  TypedStepSchemas;

{$R *.dfm}

procedure TPropertyEditorForm.FormCreate(Sender: TObject);
begin
  FRows := TObjectList<TPropertyRow>.Create(True);
end;

procedure TPropertyEditorForm.FormDestroy(Sender: TObject);
begin
  FRows.Free;
  FContext := nil;
  if Assigned(FWorking) then
    FWorking.Free;
end;

procedure TPropertyEditorForm.btnCancelClick(Sender: TObject);
begin
  // modal cancel
end;

procedure TPropertyEditorForm.ClearRows;
begin
  while ScrollBox.ControlCount > 0 do
    ScrollBox.Controls[0].Free;
  FRows.Clear;
end;

function TPropertyEditorForm.CreateRowPanel(const PropTitle: string;
  Required: Boolean): TPropertyRow;
var
  RowPanel: TPanel;
begin
  Result := TPropertyRow.Create;
  RowPanel := TPanel.Create(ScrollBox);
  RowPanel.Parent := ScrollBox;
  RowPanel.Align := alTop;
  RowPanel.Height := 56;
  RowPanel.BevelOuter := bvNone;

  Result.lblName := TLabel.Create(RowPanel);
  Result.lblName.Parent := RowPanel;
  Result.lblName.Left := 8;
  Result.lblName.Top := 8;
  Result.lblName.Width := 180;
  if Required then
    Result.lblName.Caption := PropTitle + ' *'
  else
    Result.lblName.Caption := PropTitle;

  Result.ValuePanel := TPanel.Create(RowPanel);
  Result.ValuePanel.Parent := RowPanel;
  Result.ValuePanel.Left := 196;
  Result.ValuePanel.Top := 4;
  Result.ValuePanel.Width := RowPanel.Width - 204;
  Result.ValuePanel.Height := 48;
  Result.ValuePanel.Anchors := [akLeft, akTop, akRight];
  Result.ValuePanel.BevelOuter := bvNone;

  Result.ErrorLabel := TLabel.Create(RowPanel);
  Result.ErrorLabel.Parent := RowPanel;
  Result.ErrorLabel.Left := 196;
  Result.ErrorLabel.Top := 36;
  Result.ErrorLabel.Width := RowPanel.Width - 204;
  Result.ErrorLabel.Font.Color := clMaroon;
  Result.ErrorLabel.Anchors := [akLeft, akTop, akRight];

  FRows.Add(Result);
end;

procedure TPropertyEditorForm.BuildDiscriminatorRow;
var
  Editor: ISchemaPropertyEditor;
  Row: TPropertyRow;
  Val: TJSONValue;
begin
  if not TSchemaEditorRegistry.TryResolveByName(TSchemaEditorKeys.DiscriminatorKey, Editor) then
    Exit;
  if not Editor.CanEdit(FSchema) then
    Exit;
  Row := CreateRowPanel(FSchema.DiscriminatorProperty, True);
  Row.PropertyName := FSchema.DiscriminatorProperty;
  Row.SchemaNode := FSchema;
  Row.Editor := Editor;
  Val := GetPropertyValue(FSchema.DiscriminatorProperty);
  Editor.CreateRow(FContext, Row, Val);
end;

procedure TPropertyEditorForm.BuildPropertyRows(EffectiveSchema: TSchemaNode);
var
  I: Integer;
  Prop: TSchemaProperty;
  PropNode: TSchemaNode;
  Row: TPropertyRow;
  TitleText: string;
  Val: TJSONValue;
  Editor: ISchemaPropertyEditor;
  TypedRoot: TSchemaNode;
begin
  for I := 0 to EffectiveSchema.PropertyCount - 1 do
  begin
    Prop := EffectiveSchema.Properties[I];
    if (FSchema.DiscriminatorProperty <> '') and
      SameText(Prop.Name, FSchema.DiscriminatorProperty) then
      Continue;
    PropNode := TSchemaNode(Prop.Node);
    Editor := TSchemaEditorRegistry.ResolveProperty(Prop.Name, PropNode);
    TitleText := PropNode.Title;
    if TitleText = '' then
      TitleText := Prop.Name;
    Row := CreateRowPanel(TitleText, PropNode.Required);
    Row.PropertyName := Prop.Name;
    Row.SchemaNode := PropNode;
    if TSchemaEditorKeys.IsTypedStepProperty(Prop.Name) and
      TTypedStepSchemas.TryLoadStepRoot(Prop.Name, TypedRoot) then
      Row.SchemaNode := TypedRoot;
    Row.Editor := Editor;
    if PropNode.Description <> '' then
      Row.lblName.Hint := PropNode.Description;
    Val := GetPropertyValue(Prop.Name);
    Editor.CreateRow(FContext, Row, Val);
  end;
end;

procedure TPropertyEditorForm.BuildRows;
var
  Effective: TSchemaNode;
begin
  ClearRows;
  Effective := TSchemaBranchResolver.ResolveObjectSchema(FSchema, FWorking);
  if FSchema.OneOfBranches.Count > 0 then
    BuildDiscriminatorRow;
  BuildPropertyRows(Effective);
end;

function TPropertyEditorForm.GetPropertyValue(const PropName: string): TJSONValue;
begin
  Result := FWorking.GetValue(PropName);
end;

procedure TPropertyEditorForm.SetPropertyValue(const PropName: string;
  AValue: TJSONValue);
var
  Existing: TJSONPair;
begin
  Existing := FWorking.RemovePair(PropName);
  if Assigned(Existing) then
    Existing.Free;
  FWorking.AddPair(PropName, AValue);
end;

function TPropertyEditorForm.ValidateAll(out ErrorMessage: string): Boolean;
var
  Row: TPropertyRow;
  Val: TJSONValue;
begin
  for Row in FRows do
  begin
    if Row.PropertyName = '' then
      Continue;
    if Assigned(Row.Editor) then
      Row.Editor.ReadRow(FContext, Row);
    Val := GetPropertyValue(Row.PropertyName);
    if not TSchemaValidator.ValidateValue(Row.SchemaNode, Val, ErrorMessage) then
    begin
      Row.ErrorLabel.Caption := ErrorMessage;
      Exit(False);
    end;
    Row.ErrorLabel.Caption := '';
  end;
  Result := TSchemaValidator.ValidateObject(FSchema, FWorking, ErrorMessage);
end;

procedure TPropertyEditorForm.btnOKClick(Sender: TObject);
var
  Err: string;
begin
  if not ValidateAll(Err) then
  begin
    MessageDlg(Err, TMsgDlgType.mtWarning, [TMsgDlgBtn.mbOK], 0);
    Exit;
  end;
  ModalResult := mrOk;
end;

class function TPropertyEditorForm.EditObject(AOwner: TComponent;
  const ABreadcrumb: string; ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
var
  Form: TPropertyEditorForm;
  Pair: TJSONPair;
begin
  Form := TPropertyEditorForm.Create(AOwner);
  try
    Form.FSchema := ASchema;
    Form.FObject := AObject;
    Form.FWorking := AObject.Clone as TJSONObject;
    Form.FBreadcrumb := ABreadcrumb;
    Form.FContext := TPropertyEditorContext.Create(AOwner, ASchema, ABreadcrumb,
      function(const AName: string): TJSONValue
      begin
        Result := Form.GetPropertyValue(AName);
      end,
      procedure(const AName: string; AValue: TJSONValue)
      begin
        Form.SetPropertyValue(AName, AValue);
      end,
      procedure
      begin
        Form.BuildRows;
      end);
    if ABreadcrumb <> '' then
      Form.Caption := ABreadcrumb
    else if ASchema.Title <> '' then
      Form.Caption := ASchema.Title
    else
      Form.Caption := 'Property Editor';
    Form.BuildRows;
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
