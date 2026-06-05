unit PropertyEditorForm;

interface

uses
  Winapi.Windows,
  Winapi.Messages,
  System.SysUtils,
  System.Classes,
  Spring.Collections,
  System.Math,
  Vcl.Graphics,
  Vcl.Controls,
  Vcl.Forms,
  Vcl.Dialogs,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  System.JSON,
  SchemaNode,
  SchemaBranchResolver,
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
    FRows: IList<TPropertyRow>;
    FGridHost: TPanel;
    FSelectedRow: TPropertyRow;
    FBuildingRows: Boolean;
    procedure CreatePropertyGrid;
    procedure ClearRows;
    procedure BuildRows;
    procedure BuildPropertyRows(EffectiveSchema: TSchemaNode);
    procedure BuildDiscriminatorRow;
    function CreateRowPanel(const PropTitle: string; Required: Boolean): TPropertyRow;
    procedure LayoutPropertyGrid;
    procedure PositionRowControls;
    procedure HookRowControls(ARow: TPropertyRow);
    procedure CommitRow(ARow: TPropertyRow);
    procedure CommitSelectedRow;
    procedure SelectRow(ARow: TPropertyRow);
    procedure ScrollRowIntoView(ARow: TPropertyRow);
    function GetPropertyValue(const PropName: string): TJSONValue;
    procedure SetPropertyValue(const PropName: string; AValue: TJSONValue);
    procedure ClearPropertyValue(const PropName: string);
    function ValidateAll(out ErrorMessage: string): Boolean;
  public
    class function EditObject(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
  end;

implementation

uses
  System.UITypes;

{$R *.dfm}

procedure TPropertyEditorForm.FormCreate(Sender: TObject);
begin
  FRows := TCollections.CreateObjectList<TPropertyRow>(True);
  CreatePropertyGrid;
end;

procedure TPropertyEditorForm.FormDestroy(Sender: TObject);
begin
  FRows := nil;
  FContext := nil;
  if Assigned(FWorking) then
    FWorking.Free;
end;

procedure TPropertyEditorForm.btnCancelClick(Sender: TObject);
begin
  ModalResult := mrCancel;
end;

procedure TPropertyEditorForm.CreatePropertyGrid;
begin
  ScrollBox.BorderStyle := bsNone;
  ScrollBox.HorzScrollBar.Visible := False;
  ScrollBox.VertScrollBar.Tracking := True;

  FGridHost := TPanel.Create(Self);
  FGridHost.Parent := ScrollBox;
  FGridHost.Align := alTop;
  FGridHost.BevelOuter := bvNone;
  FGridHost.Caption := '';
  FGridHost.TabOrder := 0;
  LayoutPropertyGrid;
end;

procedure TPropertyEditorForm.ClearRows;
begin
  FSelectedRow := nil;
  if Assigned(FGridHost) then
  begin
    while FGridHost.ControlCount > 0 do
      FGridHost.Controls[0].Free;
    FGridHost.Height := 0;
  end;
  FRows.Clear;
end;

function TPropertyEditorForm.CreateRowPanel(const PropTitle: string;
  Required: Boolean): TPropertyRow;
var
  CaptionText: string;
  RowPanel: TPanel;
  RowIndex: Integer;
begin
  Result := TPropertyRow.Create;
  RowIndex := FRows.Count;
  Result.GridRow := RowIndex;
  Result.DisplayName := PropTitle;

  CaptionText := PropTitle;
  if Required then
    CaptionText := CaptionText + ' *';

  RowPanel := TPanel.Create(FGridHost);
  RowPanel.Parent := FGridHost;
  RowPanel.BevelOuter := bvNone;
  RowPanel.Caption := '';
  RowPanel.Color := clBtnFace;
  RowPanel.ParentBackground := False;

  Result.lblName := TLabel.Create(RowPanel);
  Result.lblName.Parent := RowPanel;
  Result.lblName.Alignment := taLeftJustify;
  Result.lblName.AutoSize := False;
  Result.lblName.Caption := CaptionText;

  Result.ValuePanel := TPanel.Create(RowPanel);
  Result.ValuePanel.Parent := RowPanel;
  Result.ValuePanel.BevelOuter := bvNone;
  Result.ValuePanel.Caption := '';
  Result.ValuePanel.TabOrder := RowIndex;

  Result.ErrorLabel := TLabel.Create(RowPanel);
  Result.ErrorLabel.Parent := RowPanel;
  Result.ErrorLabel.Visible := False;
  Result.ErrorLabel.Font.Color := clMaroon;

  FRows.Add(Result);
  LayoutPropertyGrid;
end;

procedure TPropertyEditorForm.LayoutPropertyGrid;
begin
  if not Assigned(FGridHost) then
    Exit;
  FGridHost.Width := ScrollBox.ClientWidth;
  FGridHost.Height := Max(1, FRows.Count * 27);
  PositionRowControls;
end;

procedure TPropertyEditorForm.PositionRowControls;
var
  NameWidth: Integer;
  RowPanel: TWinControl;
  Row: TPropertyRow;
begin
  if not Assigned(FGridHost) then
    Exit;
  NameWidth := EnsureRange(ScrollBox.ClientWidth div 3, 160, 280);
  for Row in FRows do
  begin
    if not Assigned(Row.ValuePanel) then
      Continue;
    RowPanel := Row.ValuePanel.Parent;
    if Assigned(RowPanel) then
      RowPanel.SetBounds(0, Row.GridRow * 27, Max(320, ScrollBox.ClientWidth),
        27);
    if Assigned(Row.lblName) then
      Row.lblName.SetBounds(8, 5, NameWidth - 12, 17);
    Row.ValuePanel.SetBounds(NameWidth, 2,
      Max(120, ScrollBox.ClientWidth - NameWidth - 8), 23);
  end;
end;

procedure TPropertyEditorForm.HookRowControls(ARow: TPropertyRow);
var
  SelectRowProc: TNotifyEventProc;
begin
  if not Assigned(ARow) then
    Exit;
  SelectRowProc := procedure(Sender: TObject)
    begin
      if FSelectedRow <> ARow then
      begin
        CommitSelectedRow;
        FSelectedRow := ARow;
      end;
    end;
  if ARow.ValueControl is TEdit then
    TEdit(ARow.ValueControl).OnEnter := ARow.BindNotify(SelectRowProc)
  else if ARow.ValueControl is TComboBox then
    TComboBox(ARow.ValueControl).OnEnter := ARow.BindNotify(SelectRowProc)
  else if ARow.ValueControl is TCheckBox then
    TCheckBox(ARow.ValueControl).OnEnter := ARow.BindNotify(SelectRowProc);
  if Assigned(ARow.btnEdit) then
    ARow.btnEdit.OnEnter := ARow.BindNotify(SelectRowProc);
  if Assigned(ARow.btnClear) then
    ARow.btnClear.OnEnter := ARow.BindNotify(SelectRowProc);
  if Assigned(ARow.chkNull) then
    ARow.chkNull.OnEnter := ARow.BindNotify(SelectRowProc);
end;

procedure TPropertyEditorForm.CommitRow(ARow: TPropertyRow);
begin
  if FBuildingRows or not Assigned(ARow) or not Assigned(ARow.Editor) then
    Exit;
  ARow.Editor.ReadRow(FContext, ARow);
end;

procedure TPropertyEditorForm.CommitSelectedRow;
begin
  CommitRow(FSelectedRow);
end;

procedure TPropertyEditorForm.ScrollRowIntoView(ARow: TPropertyRow);
var
  RowBottom: Integer;
  RowTop: Integer;
  ViewBottom: Integer;
begin
  if not Assigned(FGridHost) or not Assigned(ARow) then
    Exit;
  RowTop := FGridHost.Top + (ARow.GridRow * 27);
  RowBottom := RowTop + 27;
  ViewBottom := ScrollBox.VertScrollBar.Position + ScrollBox.ClientHeight;
  if RowTop < ScrollBox.VertScrollBar.Position then
    ScrollBox.VertScrollBar.Position := Max(0, RowTop)
  else if RowBottom > ViewBottom then
    ScrollBox.VertScrollBar.Position := Max(0, RowBottom - ScrollBox.ClientHeight);
end;

procedure TPropertyEditorForm.SelectRow(ARow: TPropertyRow);
begin
  if not Assigned(FGridHost) or not Assigned(ARow) then
    Exit;
  ScrollRowIntoView(ARow);
  FSelectedRow := ARow;

  if not Showing then
    Exit;
  if Assigned(ARow.ValueControl) and ARow.ValueControl.Showing and
    ARow.ValueControl.Enabled and ARow.ValueControl.CanFocus then
    ARow.ValueControl.SetFocus
  else if FGridHost.Showing and FGridHost.Enabled and FGridHost.CanFocus then
    FGridHost.SetFocus;
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
  HookRowControls(Row);
  PositionRowControls;
end;

procedure TPropertyEditorForm.BuildPropertyRows(EffectiveSchema: TSchemaNode);
var
  Prop: TSchemaProperty;
  PropNode: TSchemaNode;
  Row: TPropertyRow;
  TitleText: string;
  Val: TJSONValue;
  Editor: ISchemaPropertyEditor;
begin
  for Prop in EffectiveSchema.PropertyItems do
  begin
    if (FSchema.DiscriminatorProperty <> '') and
      SameText(Prop.Name, FSchema.DiscriminatorProperty) then
      Continue;
    PropNode := TSchemaNode(Prop.Node);
    Editor := TSchemaEditorRegistry.Resolve(PropNode);
    TitleText := PropNode.Title;
    if TitleText = '' then
      TitleText := Prop.Name;
    Row := CreateRowPanel(TitleText, PropNode.Required);
    Row.PropertyName := Prop.Name;
    Row.SchemaNode := PropNode;
    Row.Editor := Editor;
    if PropNode.Description <> '' then
      Row.lblName.Hint := PropNode.Description;
    Val := GetPropertyValue(Prop.Name);
    Editor.CreateRow(FContext, Row, Val);
    HookRowControls(Row);
    PositionRowControls;
  end;
end;

procedure TPropertyEditorForm.BuildRows;
var
  Effective: TSchemaNode;
begin
  FBuildingRows := True;
  try
    ClearRows;
    Effective := TSchemaBranchResolver.ResolveObjectSchema(FSchema, FWorking);
    if FSchema.OneOfBranches.Count > 0 then
      BuildDiscriminatorRow;
    BuildPropertyRows(Effective);
    LayoutPropertyGrid;
  finally
    FBuildingRows := False;
  end;
  if FRows.Count > 0 then
    SelectRow(FRows[0]);
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
  if Assigned(AValue) then
    FWorking.AddPair(PropName, AValue);
end;

procedure TPropertyEditorForm.ClearPropertyValue(const PropName: string);
var
  Existing: TJSONPair;
begin
  Existing := FWorking.RemovePair(PropName);
  if Assigned(Existing) then
    Existing.Free;
end;

function TPropertyEditorForm.ValidateAll(out ErrorMessage: string): Boolean;
var
  Row: TPropertyRow;
  Val: TJSONValue;
begin
  CommitSelectedRow;
  for Row in FRows do
  begin
    if Row.PropertyName = '' then
      Continue;
    if Assigned(Row.Editor) then
      Row.Editor.ReadRow(FContext, Row);
    Val := GetPropertyValue(Row.PropertyName);
    if not TSchemaValidator.ValidateValue(Row.SchemaNode, Val, ErrorMessage) then
    begin
      ErrorMessage := Format('%s: %s', [Row.DisplayName, ErrorMessage]);
      Row.ErrorLabel.Caption := ErrorMessage;
      SelectRow(Row);
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

function ResolvePopupParent(AOwner: TComponent): TCustomForm;
begin
  Result := nil;
  if AOwner is TCustomForm then
    Exit(TCustomForm(AOwner));
  if AOwner is TControl then
    Result := GetParentForm(TControl(AOwner));
end;

class function TPropertyEditorForm.EditObject(AOwner: TComponent;
  const ABreadcrumb: string; ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
begin
  var PopupParent := ResolvePopupParent(AOwner);
  var Form := TPropertyEditorForm.Create(nil);
  try
    if Assigned(PopupParent) then
    begin
      Form.PopupMode := pmExplicit;
      Form.PopupParent := PopupParent;
    end;
    Form.FSchema := ASchema;
    Form.FObject := AObject;
    Form.FWorking := AObject.Clone as TJSONObject;
    Form.FBreadcrumb := ABreadcrumb;
    Form.FContext := TPropertyEditorContext.Create(Form, ASchema, ABreadcrumb,
      function(const AName: string): TJSONValue
      begin
        Result := Form.GetPropertyValue(AName);
      end,
      procedure(const AName: string; AValue: TJSONValue)
      begin
        Form.SetPropertyValue(AName, AValue);
      end,
      procedure(const AName: string)
      begin
        Form.ClearPropertyValue(AName);
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
      var Pair: TJSONPair;

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
