unit NullableRowSupport;

interface

uses
  System.Classes,
  Vcl.Controls,
  Vcl.StdCtrls,
  Vcl.ExtCtrls,
  System.JSON,
  EditorTypes,
  PropertyEditorContext,
  SchemaNode,
  SchemaDefaults,
  SchemaValueSummary;

type
  TNullableRowSupport = class
  public
    class procedure AddNullCheckbox(const AContext: IPropertyEditorContext;
      ARow: TPropertyRow; AValue: TJSONValue; AOnToggle: TNotifyEventProc);
    class procedure SetControlEnabled(ARow: TPropertyRow; AEnabled: Boolean);
    class function IsNullChecked(ARow: TPropertyRow): Boolean;
  end;

implementation

class procedure TNullableRowSupport.AddNullCheckbox(
  const AContext: IPropertyEditorContext; ARow: TPropertyRow; AValue: TJSONValue;
  AOnToggle: TNotifyEventProc);
begin
  if not ARow.SchemaNode.Nullable then
    Exit;
  ARow.chkNull := TCheckBox.Create(ARow.ValuePanel);
  ARow.chkNull.Parent := ARow.ValuePanel;
  ARow.chkNull.Align := alRight;
  ARow.chkNull.Width := 72;
  ARow.chkNull.Caption := 'Null';
  ARow.chkNull.Checked := TSchemaValueSummary.IsNullValue(AValue);
  ARow.chkNull.Tag := NativeInt(ARow);
  ARow.chkNull.OnClick := ARow.BindNotify(AOnToggle);
end;

class procedure TNullableRowSupport.SetControlEnabled(ARow: TPropertyRow;
  AEnabled: Boolean);
begin
  if Assigned(ARow.ValueControl) then
    ARow.ValueControl.Enabled := AEnabled;
end;

class function TNullableRowSupport.IsNullChecked(ARow: TPropertyRow): Boolean;
begin
  Result := Assigned(ARow.chkNull) and ARow.chkNull.Checked;
end;

end.
