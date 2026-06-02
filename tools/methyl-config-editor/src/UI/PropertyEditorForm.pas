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
  Vcl.ComCtrls,
  System.JSON,
  SchemaNode,
  SchemaBranchResolver,
  SchemaDefaults,
  SchemaValidator,
  SchemaValueSummary;

type
  TRowBinding = class
  public
    PropertyName: string;
    SchemaNode: TSchemaNode;
    lblName: TLabel;
    ValuePanel: TPanel;
    ValueControl: TWinControl;
    btnEdit: TButton;
    btnClear: TButton;
    chkNull: TCheckBox;
    ErrorLabel: TLabel;
  end;

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
    FBindings: TObjectList<TRowBinding>;
    FModalResultOK: Boolean;
    procedure ClearRows;
    procedure BuildRows;
    procedure BuildPropertyRows(EffectiveSchema: TSchemaNode);
    procedure BuildDiscriminatorRow(ANode: TSchemaNode);
    function CreateRowPanel(const PropTitle: string; Required: Boolean): TRowBinding;
    procedure BindScalar(Row: TRowBinding; AValue: TJSONValue);
    procedure BindComplex(Row: TRowBinding; AValue: TJSONValue);
    procedure ScalarChanged(Sender: TObject);
    procedure NullChanged(Sender: TObject);
    procedure EditComplexClick(Sender: TObject);
    procedure DiscriminatorChanged(Sender: TObject);
    procedure ReadScalarFromControl(Row: TRowBinding);
    function GetPropertyValue(const PropName: string): TJSONValue;
    procedure SetPropertyValue(const PropName: string; AValue: TJSONValue);
    function ValidateAll(out ErrorMessage: string): Boolean;
  public
    class function EditObject(AOwner: TComponent; const ABreadcrumb: string;
      ASchema: TSchemaNode; AObject: TJSONObject): Boolean;
  end;

implementation

uses
  JsonPath,
  ArrayEditorForm,
  DictEditorForm;

{$R *.dfm}

procedure TPropertyEditorForm.FormCreate(Sender: TObject);
begin
  FBindings := TObjectList<TRowBinding>.Create(True);
  FModalResultOK := False;
end;

procedure TPropertyEditorForm.FormDestroy(Sender: TObject);
begin
  FBindings.Free;
  if Assigned(FWorking) then
    FWorking.Free;
end;

procedure TPropertyEditorForm.btnCancelClick(Sender: TObject);
begin
  FModalResultOK := False;
end;

procedure TPropertyEditorForm.ClearRows;
begin
  while ScrollBox.ControlCount > 0 do
    ScrollBox.Controls[0].Free;
  FBindings.Clear;
end;

function TPropertyEditorForm.CreateRowPanel(const PropTitle: string;
  Required: Boolean): TRowBinding;
var
  RowPanel: TPanel;
begin
  Result := TRowBinding.Create;
  RowPanel := TPanel.Create(ScrollBox);
  RowPanel.Parent := ScrollBox;
  RowPanel.Align := alTop;
  RowPanel.Height := 56;
  RowPanel.BevelOuter := bvNone;
  RowPanel.Caption := '';

  Result.lblName := TLabel.Create(RowPanel);
  Result.lblName.Parent := RowPanel;
  Result.lblName.Left := 8;
  Result.lblName.Top := 8;
  Result.lblName.Width := 180;
  if Required then
    Result.lblName.Caption := PropTitle + ' *'
  else
    Result.lblName.Caption := PropTitle;
  Result.lblName.ShowAccelChar := False;

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
  Result.ErrorLabel.Caption := '';
  Result.ErrorLabel.Anchors := [akLeft, akTop, akRight];

  FBindings.Add(Result);
end;

procedure TPropertyEditorForm.BuildDiscriminatorRow(ANode: TSchemaNode);
var
  Row: TRowBinding;
  Combo: TComboBox;
  Key: string;
  Current: string;
  Val: TJSONValue;
begin
  if (ANode.DiscriminatorProperty = '') or (ANode.DiscriminatorMapping.Count = 0) then
    Exit;
  Row := CreateRowPanel(ANode.DiscriminatorProperty, True);
  Row.PropertyName := ANode.DiscriminatorProperty;
  Row.SchemaNode := ANode;
  Combo := TComboBox.Create(Row.ValuePanel);
  Combo.Parent := Row.ValuePanel;
  Combo.Align := alClient;
  Combo.Style := csDropDownList;
  for Key in ANode.DiscriminatorMapping.Keys do
    Combo.Items.Add(Key);
  Val := FWorking.GetValue(ANode.DiscriminatorProperty);
  if Val is TJSONString then
    Current := TJSONString(Val).Value
  else if Combo.Items.Count > 0 then
    Current := Combo.Items[0];
  Combo.ItemIndex := Combo.Items.IndexOf(Current);
  if Combo.ItemIndex < 0 then
    Combo.ItemIndex := 0;
  Combo.OnChange := DiscriminatorChanged;
  Row.ValueControl := Combo;
end;

procedure TPropertyEditorForm.BuildPropertyRows(EffectiveSchema: TSchemaNode);
var
  I: Integer;
  Prop: TSchemaProperty;
  PropNode: TSchemaNode;
  Row: TRowBinding;
  TitleText: string;
  Val: TJSONValue;
begin
  for I := 0 to EffectiveSchema.PropertyCount - 1 do
  begin
    Prop := EffectiveSchema.Properties[I];
    if (FSchema.DiscriminatorProperty <> '') and
      SameText(Prop.Name, FSchema.DiscriminatorProperty) then
      Continue;
    PropNode := TSchemaNode(Prop.Node);
    TitleText := PropNode.Title;
    if TitleText = '' then
      TitleText := Prop.Name;
    Row := CreateRowPanel(TitleText, PropNode.Required);
    Row.PropertyName := Prop.Name;
    Row.SchemaNode := PropNode;
    if PropNode.Description <> '' then
      Row.lblName.Hint := PropNode.Description;
    Val := FWorking.GetValue(Prop.Name);
    if PropNode.IsScalar then
      BindScalar(Row, Val)
    else
      BindComplex(Row, Val);
  end;
end;

procedure TPropertyEditorForm.BuildRows;
var
  Effective: TSchemaNode;
begin
  ClearRows;
  Effective := TSchemaBranchResolver.ResolveObjectSchema(FSchema, FWorking);
  if FSchema.OneOfBranches.Count > 0 then
    BuildDiscriminatorRow(FSchema);
  BuildPropertyRows(Effective);
end;

procedure TPropertyEditorForm.BindScalar(Row: TRowBinding; AValue: TJSONValue);
var
  Edit: TEdit;
  Check: TCheckBox;
  Combo: TComboBox;
  Spin: TSpinEdit;
  E: string;
begin
  if Row.SchemaNode.Nullable then
  begin
    Row.chkNull := TCheckBox.Create(Row.ValuePanel);
    Row.chkNull.Parent := Row.ValuePanel;
    Row.chkNull.Align := alRight;
    Row.chkNull.Width := 72;
    Row.chkNull.Caption := 'Null';
    Row.chkNull.Checked := TSchemaValueSummary.IsNullValue(AValue);
    Row.chkNull.Tag := NativeInt(Row);
    Row.chkNull.OnClick := NullChanged;
  end;

  case Row.SchemaNode.Kind of
    skBoolean:
      begin
        Check := TCheckBox.Create(Row.ValuePanel);
        Check.Parent := Row.ValuePanel;
        Check.Align := alClient;
        Check.Caption := '';
        if AValue is TJSONTrue then
          Check.Checked := True
        else
          Check.Checked := False;
        Check.OnClick := ScalarChanged;
        Row.ValueControl := Check;
      end;
    skInteger, skNumber:
      begin
        Spin := TSpinEdit.Create(Row.ValuePanel);
        Spin.Parent := Row.ValuePanel;
        Spin.Align := alClient;
        if AValue is TJSONNumber then
          Spin.Value := Trunc(TJSONNumber(AValue).AsDouble)
        else
          Spin.Value := 0;
        Spin.OnChange := ScalarChanged;
        Row.ValueControl := Spin;
      end;
  else
    begin
      if Length(Row.SchemaNode.EnumValues) > 0 then
      begin
        Combo := TComboBox.Create(Row.ValuePanel);
        Combo.Parent := Row.ValuePanel;
        Combo.Align := alClient;
        Combo.Style := csDropDownList;
        for E in Row.SchemaNode.EnumValues do
          Combo.Items.Add(E);
        if AValue is TJSONString then
          Combo.ItemIndex := Combo.Items.IndexOf(TJSONString(AValue).Value)
        else
          Combo.ItemIndex := 0;
        if Combo.ItemIndex < 0 then
          Combo.ItemIndex := 0;
        Combo.OnChange := ScalarChanged;
        Row.ValueControl := Combo;
      end
      else
      begin
        Edit := TEdit.Create(Row.ValuePanel);
        Edit.Parent := Row.ValuePanel;
        Edit.Align := alClient;
        if AValue is TJSONString then
          Edit.Text := TJSONString(AValue).Value
        else if not TSchemaValueSummary.IsNullValue(AValue) then
          Edit.Text := AValue.Value;
        Edit.OnChange := ScalarChanged;
        Row.ValueControl := Edit;
      end;
    end;
  end;

  if Assigned(Row.chkNull) then
  begin
    Row.chkNull.Tag := NativeInt(Row);
    if Row.ValueControl <> nil then
      Row.ValueControl.Enabled := not Row.chkNull.Checked;
  end;
end;

procedure TPropertyEditorForm.BindComplex(Row: TRowBinding; AValue: TJSONValue);
var
  Summary: TEdit;
begin
  Summary := TEdit.Create(Row.ValuePanel);
  Summary.Parent := Row.ValuePanel;
  Summary.Align := alClient;
  Summary.ReadOnly := True;
  Summary.Text := TSchemaValueSummary.Describe(Row.SchemaNode, AValue);
  Row.ValueControl := Summary;

  Row.btnEdit := TButton.Create(Row.ValuePanel);
  Row.btnEdit.Parent := Row.ValuePanel;
  Row.btnEdit.Align := alRight;
  Row.btnEdit.Width := 75;
  Row.btnEdit.Caption := 'Edit...';
  Row.btnEdit.Tag := NativeInt(Row);
  Row.btnEdit.OnClick := EditComplexClick;

  if Row.SchemaNode.Nullable then
  begin
    Row.btnClear := TButton.Create(Row.ValuePanel);
    Row.btnClear.Parent := Row.ValuePanel;
    Row.btnClear.Align := alRight;
    Row.btnClear.Width := 60;
    Row.btnClear.Caption := 'Null';
    Row.btnClear.Tag := NativeInt(Row);
    Row.btnClear.OnClick := NullChanged;
  end;
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

procedure TPropertyEditorForm.ReadScalarFromControl(Row: TRowBinding);
var
  NewVal: TJSONValue;
  Edit: TEdit;
  Check: TCheckBox;
  Combo: TComboBox;
  Spin: TSpinEdit;
begin
  if Assigned(Row.chkNull) and Row.chkNull.Checked then
  begin
    SetPropertyValue(Row.PropertyName, TJSONNull.Create);
    Exit;
  end;
  case Row.SchemaNode.Kind of
    skBoolean:
      begin
        Check := TCheckBox(Row.ValueControl);
        if Check.Checked then
          NewVal := TJSONTrue.Create
        else
          NewVal := TJSONFalse.Create;
      end;
    skInteger, skNumber:
      begin
        Spin := TSpinEdit(Row.ValueControl);
        NewVal := TJSONNumber.Create(Spin.Value);
      end;
  else
    if Row.ValueControl is TComboBox then
    begin
      Combo := TComboBox(Row.ValueControl);
      NewVal := TJSONString.Create(Combo.Text);
    end
    else
    begin
      Edit := TEdit(Row.ValueControl);
      NewVal := TJSONString.Create(Edit.Text);
    end;
  end;
  SetPropertyValue(Row.PropertyName, NewVal);
end;

procedure TPropertyEditorForm.ScalarChanged(Sender: TObject);
var
  Row: TRowBinding;
begin
  for Row in FBindings do
    if Row.ValueControl = Sender then
    begin
      ReadScalarFromControl(Row);
      Exit;
    end;
end;

procedure TPropertyEditorForm.NullChanged(Sender: TObject);
var
  Row: TRowBinding;
  Edit: TEdit;
begin
  Row := TRowBinding(Pointer(TControl(Sender).Tag));
  if Sender = Row.chkNull then
  begin
    if Row.chkNull.Checked then
    begin
      SetPropertyValue(Row.PropertyName, TJSONNull.Create);
      if Assigned(Row.ValueControl) then
        Row.ValueControl.Enabled := False;
    end
    else
    begin
      SetPropertyValue(Row.PropertyName, TSchemaDefaults.CreateDefaultValue(Row.SchemaNode));
      if Assigned(Row.ValueControl) then
        Row.ValueControl.Enabled := True;
      BindScalar(Row, GetPropertyValue(Row.PropertyName));
    end;
  end
  else if Sender = Row.btnClear then
  begin
    SetPropertyValue(Row.PropertyName, TJSONNull.Create);
    if Row.ValueControl is TEdit then
    begin
      Edit := TEdit(Row.ValueControl);
      Edit.Text := TSchemaValueSummary.Describe(Row.SchemaNode, nil);
    end;
  end;
end;

procedure TPropertyEditorForm.DiscriminatorChanged(Sender: TObject);
var
  Combo: TComboBox;
  DiscValue: string;
begin
  Combo := TComboBox(Sender);
  if Combo.ItemIndex < 0 then
    Exit;
  DiscValue := Combo.Items[Combo.ItemIndex];
  SetPropertyValue(FSchema.DiscriminatorProperty, TJSONString.Create(DiscValue));
  BuildRows;
end;

procedure TPropertyEditorForm.EditComplexClick(Sender: TObject);
var
  Row: TRowBinding;
  Val: TJSONValue;
  Obj: TJSONObject;
  Arr: TJSONArray;
  CloneObj: TJSONObject;
  ChildTitle: string;
  ItemSchema: TSchemaNode;
begin
  Row := TRowBinding(Pointer(TButton(Sender).Tag));
  Val := GetPropertyValue(Row.PropertyName);
  ChildTitle := FBreadcrumb + ' › ' + Row.lblName.Caption;

  case Row.SchemaNode.Kind of
    skObject:
      begin
        if Val is TJSONObject then
          Obj := TJSONObject(Val)
        else
        begin
          Obj := TSchemaDefaults.CreateDefaultObject(Row.SchemaNode);
          SetPropertyValue(Row.PropertyName, Obj);
        end;
        CloneObj := Obj.Clone as TJSONObject;
        try
          ItemSchema := Row.SchemaNode;
          if Row.SchemaNode.OneOfBranches.Count > 0 then
            ItemSchema := Row.SchemaNode
          else
            ItemSchema := Row.SchemaNode;
          if TPropertyEditorForm.EditObject(Self, ChildTitle, ItemSchema, CloneObj) then
          begin
            SetPropertyValue(Row.PropertyName, CloneObj.Clone as TJSONObject);
            if Row.ValueControl is TEdit then
              TEdit(Row.ValueControl).Text :=
                TSchemaValueSummary.Describe(Row.SchemaNode, GetPropertyValue(Row.PropertyName));
          end;
        finally
          CloneObj.Free;
        end;
      end;
    skArray:
      begin
        if Val is TJSONArray then
          Arr := TJSONArray(Val)
        else
        begin
          Arr := TJSONArray.Create;
          SetPropertyValue(Row.PropertyName, Arr);
        end;
        if TArrayEditorForm.EditArray(Self, ChildTitle, Row.SchemaNode, Arr) then
          if Row.ValueControl is TEdit then
            TEdit(Row.ValueControl).Text :=
              TSchemaValueSummary.Describe(Row.SchemaNode, GetPropertyValue(Row.PropertyName));
      end;
    skDictionary:
      begin
        if Val is TJSONObject then
          Obj := TJSONObject(Val)
        else
        begin
          Obj := TJSONObject.Create;
          SetPropertyValue(Row.PropertyName, Obj);
        end;
        if TDictEditorForm.EditDictionary(Self, ChildTitle, Row.SchemaNode, Obj) then
          if Row.ValueControl is TEdit then
            TEdit(Row.ValueControl).Text :=
              TSchemaValueSummary.Describe(Row.SchemaNode, GetPropertyValue(Row.PropertyName));
      end;
  end;
end;

function TPropertyEditorForm.ValidateAll(out ErrorMessage: string): Boolean;
var
  Row: TRowBinding;
  Val: TJSONValue;
begin
  for Row in FBindings do
  begin
    if Row.PropertyName = '' then
      Continue;
    if Row.SchemaNode.IsScalar then
      ReadScalarFromControl(Row);
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
  FModalResultOK := True;
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
