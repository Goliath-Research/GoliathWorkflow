unit DiscriminatorSchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TDiscriminatorSchemaEditor = class(TAbstractSchemaEditor)
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
  Vcl.StdCtrls;

class function TDiscriminatorSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.DiscriminatorKey;
end;

function TDiscriminatorSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := Assigned(ANode) and (ANode.DiscriminatorProperty <> '') and
    (ANode.DiscriminatorMapping.Count > 0);
end;

procedure TDiscriminatorSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue);
var
  Combo: TComboBox;
  Key, Current: string;
  Val: TJSONValue;
  Schema: TSchemaNode;
begin
  Schema := AContext.GetObjectSchema;
  Combo := TComboBox.Create(ARow.ValuePanel);
  Combo.Parent := ARow.ValuePanel;
  Combo.Align := alClient;
  Combo.Style := csDropDownList;
  for Key in Schema.DiscriminatorMapping.Keys do
    Combo.Items.Add(Key);
  Val := AContext.GetPropertyValue(Schema.DiscriminatorProperty);
  if Val is TJSONString then
    Current := TJSONString(Val).Value
  else if Combo.Items.Count > 0 then
    Current := Combo.Items[0];
  Combo.ItemIndex := Combo.Items.IndexOf(Current);
  if Combo.ItemIndex < 0 then
    Combo.ItemIndex := 0;
  Combo.Tag := NativeInt(ARow);
  Combo.OnChange := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
      AContext.RebuildRows;
    end);
  ARow.ValueControl := Combo;
end;

procedure TDiscriminatorSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
var
  Combo: TComboBox;
  Schema: TSchemaNode;
begin
  Schema := AContext.GetObjectSchema;
  if not (ARow.ValueControl is TComboBox) then
    Exit;
  Combo := TComboBox(ARow.ValueControl);
  if Combo.ItemIndex < 0 then
    Exit;
  AContext.SetPropertyValue(Schema.DiscriminatorProperty,
    TJSONString.Create(Combo.Items[Combo.ItemIndex]));
end;

end.
