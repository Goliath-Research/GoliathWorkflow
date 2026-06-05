unit EnumSchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TEnumSchemaEditor = class(TAbstractSchemaEditor)
  public
    class function EditorKey: string; static;
    function CanEdit(ANode: TSchemaNode): Boolean; override;
    procedure CreateRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow;
      AValue: TJSONValue); override;
    procedure ReadRow(const AContext: IPropertyEditorContext; ARow: TPropertyRow); override;
  end;

implementation

uses
  Vcl.Controls,
  Vcl.StdCtrls,
  SchemaValueSummary;

class function TEnumSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.EnumKey;
end;

function TEnumSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skString) and
    (ANode.EnumValues.Count > 0);
end;

procedure TEnumSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue);
var
  Combo: TComboBox;
  E: string;
begin
  Combo := TComboBox.Create(ARow.ValuePanel);
  Combo.Parent := ARow.ValuePanel;
  Combo.Align := alClient;
  Combo.Style := csDropDown;
  for E in ARow.SchemaNode.EnumValues do
    Combo.Items.Add(E);
  if AValue is TJSONString then
    Combo.Text := TJSONString(AValue).Value
  else if TSchemaValueSummary.IsNullValue(AValue) then
    Combo.Text := ''
  else
    Combo.Text := AValue.Value;
  Combo.Tag := NativeInt(ARow);
  Combo.OnChange := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end);
  ARow.ValueControl := Combo;
end;

procedure TEnumSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  if ARow.ValueControl is TComboBox then
  begin
    if TComboBox(ARow.ValueControl).Text = '' then
    begin
      if ARow.SchemaNode.Nullable then
        AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create)
      else
        AContext.ClearPropertyValue(ARow.PropertyName);
      Exit;
    end;
    AContext.SetPropertyValue(ARow.PropertyName,
      TJSONString.Create(TComboBox(ARow.ValueControl).Text));
  end;
end;

end.
