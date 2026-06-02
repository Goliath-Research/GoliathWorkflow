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
  Vcl.StdCtrls,
  NullableRowSupport,
  SchemaDefaults,
  SchemaValueSummary;

class function TEnumSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.EnumKey;
end;

function TEnumSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skString) and
    (Length(ANode.EnumValues) > 0);
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
  Combo.Style := csDropDownList;
  for E in ARow.SchemaNode.EnumValues do
    Combo.Items.Add(E);
  if AValue is TJSONString then
    Combo.ItemIndex := Combo.Items.IndexOf(TJSONString(AValue).Value)
  else
    Combo.ItemIndex := 0;
  if Combo.ItemIndex < 0 then
    Combo.ItemIndex := 0;
  Combo.Tag := NativeInt(ARow);
  Combo.OnChange := procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end;
  ARow.ValueControl := Combo;
  TNullableRowSupport.AddNullCheckbox(AContext, ARow, AValue,
    procedure(Sender: TObject)
    begin
      if TNullableRowSupport.IsNullChecked(ARow) then
      begin
        AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
        TNullableRowSupport.SetControlEnabled(ARow, False);
      end
      else
      begin
        AContext.SetPropertyValue(ARow.PropertyName,
          TSchemaDefaults.CreateDefaultValue(ARow.SchemaNode));
        TNullableRowSupport.SetControlEnabled(ARow, True);
        CreateRow(AContext, ARow, AContext.GetPropertyValue(ARow.PropertyName));
      end;
    end);
  TNullableRowSupport.SetControlEnabled(ARow, not TNullableRowSupport.IsNullChecked(ARow));
end;

procedure TEnumSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  if TNullableRowSupport.IsNullChecked(ARow) then
  begin
    AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create);
    Exit;
  end;
  if ARow.ValueControl is TComboBox then
    AContext.SetPropertyValue(ARow.PropertyName,
      TJSONString.Create(TComboBox(ARow.ValueControl).Text));
end;

end.
