unit StringSchemaEditor;

interface

uses
  AbstractSchemaEditor,
  EditorTypes,
  PropertyEditorContext,
  SchemaEditorKeys,
  SchemaNode,
  System.JSON;

type
  TStringSchemaEditor = class(TAbstractSchemaEditor)
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

class function TStringSchemaEditor.EditorKey: string;
begin
  Result := TSchemaEditorKeys.StringKey;
end;

function TStringSchemaEditor.CanEdit(ANode: TSchemaNode): Boolean;
begin
  Result := inherited CanEdit(ANode) and (ANode.Kind = skString) and
    (ANode.EnumValues.Count = 0);
end;

procedure TStringSchemaEditor.CreateRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow; AValue: TJSONValue);
var
  Edit: TEdit;
begin
  Edit := TEdit.Create(ARow.ValuePanel);
  Edit.Parent := ARow.ValuePanel;
  Edit.Align := alClient;
  if AValue is TJSONString then
    Edit.Text := TJSONString(AValue).Value
  else if not TSchemaValueSummary.IsNullValue(AValue) then
    Edit.Text := AValue.Value;
  Edit.Tag := NativeInt(ARow);
  Edit.OnChange := ARow.BindNotify(procedure(Sender: TObject)
    begin
      ReadRow(AContext, ARow);
    end);
  ARow.ValueControl := Edit;
end;

procedure TStringSchemaEditor.ReadRow(const AContext: IPropertyEditorContext;
  ARow: TPropertyRow);
begin
  if ARow.ValueControl is TEdit then
  begin
    if TEdit(ARow.ValueControl).Text = '' then
    begin
      if ARow.SchemaNode.Nullable then
        AContext.SetPropertyValue(ARow.PropertyName, TJSONNull.Create)
      else
        AContext.ClearPropertyValue(ARow.PropertyName);
      Exit;
    end;
    AContext.SetPropertyValue(ARow.PropertyName,
      TJSONString.Create(TEdit(ARow.ValueControl).Text));
  end;
end;

end.
